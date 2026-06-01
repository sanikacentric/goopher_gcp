"""
GOOPHER Guardian — a self-healing agent.

Wraps critical operations (the Gemini/Vertex LLM, the catalog data layer, the
fulfillment pipeline) in a resilience policy and AUTONOMOUSLY recovers from
failures, streaming every recovery to the dev portal so a stakeholder can watch
it happen live:

    DETECT  →  DIAGNOSE  →  REMEDIATE  →  VERIFY

Patterns implemented (the production-grade vocabulary):
  * Circuit breaker        — stop hammering a failing dependency; probe to reopen.
  * Retry with backoff     — ride out transient blips.
  * Failover / graceful degrade — serve from a fallback so the customer never errors.
  * Self-repair            — fix the root cause (e.g. re-seed a stale catalog).
  * Health probes          — synthetic checks that heal a component *before* a
                             customer hits the fault, and "heal forward" to the
                             primary once it recovers.

CHAOS: a built-in fault injector (`Chaos`) lets the demo break a subsystem on
demand ("Kill Vertex") so the self-healing is repeatable and visible. Injected
faults are simulated deterministically, so the demo never depends on a real
outage.

This is intentionally dependency-free and thread-safe (a Cloud Run instance may
serve concurrent requests).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..observability.telemetry import incr, log_event

# Components Guardian watches (shown as the health strip in /dev).
COMPONENTS = ("vertex", "catalog", "fulfillment")

# Human labels + the heal playbook (diagnosis + remediation summary) per component.
_PLAYBOOK = {
    "vertex": {
        "label": "Gemini / Vertex AI",
        "diagnose": "LLM provider unavailable (Vertex 5xx / empty / timeout)",
        "remedy": "retry with backoff → fail over to the secondary recognizer / "
                  "deterministic path (serve last-known-good)",
    },
    "catalog": {
        "label": "Catalog (Firestore)",
        "diagnose": "catalog read failed or returned empty (stale / unreachable)",
        "remedy": "self-repair: re-seed the catalog from goopher_catalog.json, then retry",
    },
    "fulfillment": {
        "label": "Order fulfillment",
        "diagnose": "a fulfillment stage failed",
        "remedy": "retry the stage with backoff; compensate if it can't complete",
    },
}


class ChaosError(RuntimeError):
    """Raised by an injected chaos fault (a simulated outage)."""


class Chaos:
    """On-demand fault injector for the demo. Thread-safe."""

    def __init__(self):
        self._faults: dict[str, str] = {}
        self._lock = threading.Lock()

    def inject(self, component: str, fault: str = "outage") -> None:
        with self._lock:
            self._faults[component] = fault
        log_event("chaos_injected", component=component, fault=fault)

    def clear(self, component: str) -> None:
        with self._lock:
            self._faults.pop(component, None)
        log_event("chaos_cleared", component=component)

    def active(self, component: str) -> Optional[str]:
        with self._lock:
            return self._faults.get(component)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._faults)

    def check(self, component: str) -> None:
        """Raise a simulated outage if this component is currently faulted."""
        fault = self.active(component)
        if fault:
            raise ChaosError(f"[chaos] {component} {fault} (injected fault)")


@dataclass
class _Comp:
    state: str = "healthy"        # healthy | healing | down
    detail: str = "operational"
    failures: int = 0             # consecutive failures (circuit breaker)
    open_until: float = 0.0       # circuit-open cooldown deadline (epoch s)
    heals: int = 0                # total heals performed
    last_event: str = ""          # last heal/recovery summary
    updated: float = field(default_factory=lambda: 0.0)


class Guardian:
    """The self-healing controller."""

    _FAIL_THRESHOLD = 2           # consecutive failures → open the circuit
    _COOLDOWN_S = 8.0             # how long the circuit stays open before probing
    _MAX_RETRIES = 2              # retries inside one heal before failover
    _BACKOFF_S = 0.15            # base backoff (kept small so the demo is snappy)

    def __init__(self):
        self.chaos = Chaos()
        self._comps: dict[str, _Comp] = {c: _Comp(updated=_now()) for c in COMPONENTS}
        # Default probe: a component is recovered once its chaos fault is cleared.
        self._probes: dict[str, Callable[[], None]] = {
            c: (lambda comp=c: self.chaos.check(comp)) for c in COMPONENTS
        }
        self._lock = threading.Lock()

    # --- health introspection (for /dev/health) --- #
    def health(self) -> dict:
        with self._lock:
            comps = {
                c: {
                    "state": cc.state, "detail": cc.detail, "heals": cc.heals,
                    "last_event": cc.last_event,
                    "circuit": "open" if cc.open_until > _now() else "closed",
                }
                for c, cc in self._comps.items()
            }
        overall = "healthy"
        if any(v["state"] == "down" for v in comps.values()):
            overall = "degraded"
        elif any(v["state"] == "healing" for v in comps.values()):
            overall = "healing"
        return {"overall": overall, "components": comps,
                "labels": {c: _PLAYBOOK[c]["label"] for c in COMPONENTS},
                "chaos": self.chaos.snapshot()}

    def register_probe(self, component: str, probe: Callable[[], None]) -> None:
        """A synthetic check used to verify recovery / heal forward."""
        self._probes[component] = probe

    # --- the core: run an operation with self-healing --- #
    def protect(self, component: str, primary: Callable[[], Any], *,
                fallback: Optional[Callable[[], Any]] = None,
                repair: Optional[Callable[[], None]] = None,
                label: str = "") -> Any:
        """
        Run `primary()` with self-healing. On failure:
          1) DETECT + open the circuit after repeated failures,
          2) DIAGNOSE (from the playbook),
          3) REMEDIATE — optional repair() (e.g. re-seed) + retry with backoff,
             then fail over to `fallback()`,
          4) VERIFY — mark the component healthy/healing and stream the heal.
        Returns the primary result, or the fallback result if it had to fail over.
        """
        cc = self._comps[component]

        # Circuit OPEN → skip the known-bad primary, serve the fallback directly.
        if cc.open_until > _now() and fallback is not None:
            incr("guardian_shortcircuit_total")
            return fallback()

        try:
            result = primary()
            self._on_success(component)
            return result
        except Exception as exc:  # noqa: BLE001 — self-healing is the whole point
            return self._heal(component, exc, primary, fallback, repair, label)

    def _heal(self, component, exc, primary, fallback, repair, label) -> Any:
        from ..observability.flow_recorder import TurnTrace
        incr("guardian_heals_total")
        pb = _PLAYBOOK.get(component, {})
        ft = TurnTrace(kind="heal")
        ft.record.user_message = f"⚠️ fault in {pb.get('label', component)}"
        ft.record.customer_id = "guardian"
        ft.step("heal", "1. DETECT",
                f"{label or component} failed: {type(exc).__name__}: {str(exc)[:160]}")
        self._mark(component, "healing", f"fault: {str(exc)[:80]}")
        self._bump_failure(component)
        ft.step("heal", "2. DIAGNOSE", pb.get("diagnose", "unknown fault"))

        # 3) REMEDIATE — self-repair (root cause) then retry with backoff.
        if repair is not None:
            try:
                repair()
                ft.step("heal", "3. REMEDIATE · self-repair", pb.get("remedy", "repaired"))
            except Exception as rexc:  # noqa: BLE001
                ft.step("heal", "3. REMEDIATE · self-repair FAILED", str(rexc)[:120])

        result, recovered, via = None, False, ""
        for attempt in range(1, self._MAX_RETRIES + 1):
            time.sleep(self._BACKOFF_S * attempt)
            try:
                result = primary()
                recovered, via = True, f"retry #{attempt}"
                ft.step("heal", "3. REMEDIATE · retry", f"succeeded on {via}")
                break
            except Exception as rexc:  # noqa: BLE001
                ft.step("heal", f"3. REMEDIATE · retry #{attempt} failed",
                        f"{type(rexc).__name__}: {str(rexc)[:100]}")

        # Still failing → fail over so the CUSTOMER never sees an error.
        if not recovered and fallback is not None:
            try:
                result = fallback()
                recovered, via = True, "failover"
                ft.step("heal", "3. REMEDIATE · failover",
                        "served from the fallback path — customer unaffected")
            except Exception as fexc:  # noqa: BLE001
                ft.step("heal", "3. REMEDIATE · failover FAILED", str(fexc)[:120])

        # 4) VERIFY.
        if recovered:
            # If we recovered via retry the primary is healthy; via failover we're
            # degraded-but-serving until the background probe heals forward.
            state = "healthy" if via.startswith("retry") else "healing"
            detail = ("recovered on the primary" if state == "healthy"
                      else "degraded → serving via failover; probing to heal forward")
            self._mark(component, state, detail)
            if state == "healthy":
                self._reset_circuit(component)
            ft.step("heal", "4. VERIFY", f"{detail} (via {via})")
            ft.record.reply = f"✅ self-healed via {via}"
        else:
            self._mark(component, "down", "no fallback succeeded")
            ft.step("heal", "4. VERIFY", "could not recover — escalated")
            ft.record.reply = "❌ unrecovered"

        with self._lock:
            self._comps[component].heals += 1
            self._comps[component].last_event = ft.record.reply
        ft.commit()
        log_event("guardian_heal", component=component, recovered=recovered, via=via)

        if not recovered:
            raise exc  # genuinely unrecoverable — let the caller handle it
        return result

    # --- isolated demo driver --- #
    def simulate(self, component: str) -> dict:
        """
        Drive a SYNTHETIC transaction through `component` (a "synthetic monitor"
        request) so the self-healing is visible on demand. Fully isolated: it
        touches NO real flow (/chat, /vision, checkout) — it exercises Guardian's
        own resilience policy against a simulated unit of work. Under an injected
        chaos fault the primary fails and Guardian heals (retry → failover).
        """
        if component not in COMPONENTS:
            return {"ok": False, "error": f"unknown component {component!r}"}

        def primary():
            self.chaos.check(component)          # simulated outage if injected
            return {"served_by": "primary"}

        def fallback():                          # always succeeds → customer safe
            return {"served_by": "failover"}

        # Catalog's remediation is a (simulated) self-repair / re-seed step.
        repair = (lambda: log_event("guardian_sim_repair", component=component)
                  if component == "catalog" else None)
        result = self.protect(component, primary, fallback=fallback,
                              repair=repair if component == "catalog" else None,
                              label=f"{component}.synthetic_request")
        return {"ok": True, "component": component, "result": result,
                "health": self.health()}

    # --- background self-healing: probe + heal forward --- #
    def tick(self) -> None:
        """Probe components that aren't healthy; if their fault is gone, heal
        forward to the primary and close the circuit. Called periodically."""
        from ..observability.flow_recorder import TurnTrace
        for component in COMPONENTS:
            cc = self._comps[component]
            if cc.state == "healthy":
                continue
            probe = self._probes.get(component)
            if probe is None:
                continue
            try:
                probe()  # raises if still unhealthy (e.g. chaos still injected)
            except Exception:  # noqa: BLE001 — still down, keep waiting
                continue
            # Recovered!
            self._mark(component, "healthy", "operational")
            self._reset_circuit(component)
            with self._lock:
                self._comps[component].last_event = "🟢 healed forward to primary"
            ft = TurnTrace(kind="heal")
            ft.record.customer_id = "guardian"
            ft.record.user_message = f"probe: {_PLAYBOOK[component]['label']}"
            ft.record.reply = "🟢 recovered — circuit closed"
            ft.step("heal", "PROBE", "synthetic health check passed")
            ft.step("heal", "HEAL FORWARD",
                    "primary is back → closed the circuit, restored to primary")
            ft.commit()
            log_event("guardian_heal_forward", component=component)

    # --- internals --- #
    def _on_success(self, component: str) -> None:
        with self._lock:
            cc = self._comps[component]
            cc.failures = 0
            if cc.state != "healthy":
                cc.state, cc.detail, cc.updated = "healthy", "operational", _now()

    def _bump_failure(self, component: str) -> None:
        with self._lock:
            cc = self._comps[component]
            cc.failures += 1
            if cc.failures >= self._FAIL_THRESHOLD:
                cc.open_until = _now() + self._COOLDOWN_S  # trip the breaker

    def _reset_circuit(self, component: str) -> None:
        with self._lock:
            cc = self._comps[component]
            cc.failures, cc.open_until = 0, 0.0

    def _mark(self, component: str, state: str, detail: str) -> None:
        with self._lock:
            cc = self._comps[component]
            cc.state, cc.detail, cc.updated = state, detail, _now()


def _now() -> float:
    return time.time()


_guardian: Optional[Guardian] = None


def get_guardian() -> Guardian:
    global _guardian
    if _guardian is None:
        _guardian = Guardian()
    return _guardian
