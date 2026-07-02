"""V2 — archetype-routed dcf_role tests (pure config/mapping logic, no network).

Run: pytest scripts/test_dcf_role_routing.py -v
"""

import target_engine as te


def test_default_dcf_role_by_archetype():
    assert te._default_dcf_role_for_archetype("transformational") == "downside_floor"
    assert te._default_dcf_role_for_archetype("Transformational") == "downside_floor"  # case-insensitive
    assert te._default_dcf_role_for_archetype("garp") == "primary"
    assert te._default_dcf_role_for_archetype("cyclical") == "primary"
    assert te._default_dcf_role_for_archetype("compounder") == "primary"
    assert te._default_dcf_role_for_archetype(None) == "primary"


def test_override_loaders_handle_both_forms(monkeypatch):
    # Inject a cache with the string form (current) AND the object form (V2).
    monkeypatch.setattr(te, "_ARCHETYPE_OVERRIDES_CACHE", {
        "LITE": "transformational",                                   # string form
        "FOO": {"archetype": "garp", "dcf_role": "downside_floor"},   # object form
        "BAR": {"archetype": "compounder"},                          # object, no dcf_role
    })
    # archetype resolves for both forms
    assert te._load_archetype_override("LITE") == "transformational"
    assert te._load_archetype_override("foo") == "garp"          # case-insensitive ticker
    assert te._load_archetype_override("BAR") == "compounder"
    assert te._load_archetype_override("ZZZ") is None
    # dcf_role override only from the object form
    assert te._load_dcf_role_override("FOO") == "downside_floor"
    assert te._load_dcf_role_override("LITE") is None   # string form -> no explicit dcf_role
    assert te._load_dcf_role_override("BAR") is None


def test_routing_precedence_logic(monkeypatch):
    # Simulate build_target's resolution: explicit > per-ticker override > archetype default.
    monkeypatch.setattr(te, "_ARCHETYPE_OVERRIDES_CACHE", {
        "FOO": {"archetype": "garp", "dcf_role": "downside_floor"},  # garp but pinned to floor
    })

    def resolve(ticker, archetype, explicit=None):
        if explicit is not None:
            return explicit
        return te._load_dcf_role_override(ticker) or te._default_dcf_role_for_archetype(archetype)

    # per-ticker override beats the archetype default (garp would be 'primary')
    assert resolve("FOO", "garp") == "downside_floor"
    # transformational with no per-ticker override -> archetype default
    assert resolve("LITE", "transformational") == "downside_floor"
    # plain garp -> primary
    assert resolve("XYZ", "garp") == "primary"
    # explicit arg wins over everything
    assert resolve("LITE", "transformational", explicit="primary") == "primary"
