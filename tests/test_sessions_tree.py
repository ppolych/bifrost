"""Group/session mutation API on SessionManager.

Covers the create / rename / duplicate operations that back the sidebar's
new context-menu actions. Pure data-layer tests — no Qt context needed.
"""

import pytest

import core.persistence as persistence


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    s = persistence.SessionManager()
    # Replace the seeded defaults with a known shape so assertions are stable.
    s.sessions = {
        "Group A": [
            {"name": "alpha", "type": "SSH", "host": "1.1.1.1"},
            {"name": "beta", "type": "SSH", "host": "2.2.2.2"},
        ],
        "Group B": {
            "Sub-1": [
                {"name": "gamma", "type": "SSH", "host": "3.3.3.3"},
            ],
        },
        "Empty list": [],
        "Empty dict": {},
    }
    s.save()
    return s


# ----- add_subgroup -----

def test_add_subgroup_at_root(sm):
    name = sm.add_subgroup([], "New Group")
    assert name == "New Group"
    assert "New Group" in sm.sessions
    assert sm.sessions["New Group"] == []

def test_add_subgroup_uniquifies(sm):
    sm.add_subgroup([], "Dupe")
    second = sm.add_subgroup([], "Dupe")
    assert second == "Dupe (2)"
    third = sm.add_subgroup([], "Dupe")
    assert third == "Dupe (3)"

def test_add_subgroup_inside_dict_folder(sm):
    name = sm.add_subgroup(["Group B"], "Sub-2")
    assert name == "Sub-2"
    assert "Sub-2" in sm.sessions["Group B"]

def test_add_subgroup_refuses_when_folder_has_sessions(sm):
    with pytest.raises(ValueError):
        sm.add_subgroup(["Group A"], "doomed")

def test_add_subgroup_converts_empty_list_to_dict(sm):
    name = sm.add_subgroup(["Empty list"], "child")
    assert name == "child"
    assert isinstance(sm.sessions["Empty list"], dict)
    assert "child" in sm.sessions["Empty list"]

def test_add_subgroup_unknown_parent_returns_none(sm):
    assert sm.add_subgroup(["Nope"], "x") is None


# ----- add_session_at -----

def test_add_session_at_list_folder(sm):
    name = sm.add_session_at(["Group A"], {"name": "delta", "type": "SSH"})
    assert name == "delta"
    assert any(s["name"] == "delta" for s in sm.sessions["Group A"])

def test_add_session_at_uniquifies_session_name(sm):
    name = sm.add_session_at(["Group A"], {"name": "alpha", "type": "SSH"})
    assert name == "alpha (2)"
    assert [s["name"] for s in sm.sessions["Group A"]].count("alpha") == 1

def test_add_session_at_refuses_when_folder_has_subgroups(sm):
    with pytest.raises(ValueError):
        sm.add_session_at(["Group B"], {"name": "doomed", "type": "SSH"})

def test_add_session_at_converts_empty_dict_to_list(sm):
    sm.add_session_at(["Empty dict"], {"name": "first", "type": "SSH"})
    assert isinstance(sm.sessions["Empty dict"], list)
    assert sm.sessions["Empty dict"][0]["name"] == "first"


# ----- rename_folder -----

def test_rename_folder_keeps_position(sm):
    keys_before = list(sm.sessions.keys())
    idx = keys_before.index("Group A")
    assert sm.rename_folder(["Group A"], "Group A!") is True
    keys_after = list(sm.sessions.keys())
    assert keys_after[idx] == "Group A!"
    assert "Group A" not in sm.sessions

def test_rename_folder_refuses_on_collision(sm):
    with pytest.raises(ValueError):
        sm.rename_folder(["Group A"], "Group B")

def test_rename_folder_nested(sm):
    assert sm.rename_folder(["Group B", "Sub-1"], "Sub-One") is True
    assert "Sub-One" in sm.sessions["Group B"]
    assert "Sub-1" not in sm.sessions["Group B"]


# ----- rename_session -----

def test_rename_session(sm):
    session = sm.sessions["Group A"][0]  # alpha
    assert sm.rename_session(["Group A"], session, "alpha-prime") is True
    assert session["name"] == "alpha-prime"

def test_rename_session_refuses_on_collision(sm):
    session = sm.sessions["Group A"][0]
    with pytest.raises(ValueError):
        sm.rename_session(["Group A"], session, "beta")


def test_update_session_preserves_position(sm):
    session = sm.sessions["Group A"][0]
    assert sm.update_session(["Group A"], session, {"name": "alpha-new", "type": "SSH", "host": "h"})
    assert sm.sessions["Group A"][0]["name"] == "alpha-new"
    assert sm.sessions["Group A"][0]["host"] == "h"


def test_update_session_refuses_name_collision(sm):
    session = sm.sessions["Group A"][0]
    with pytest.raises(ValueError):
        sm.update_session(["Group A"], session, {"name": "beta", "type": "SSH"})


# ----- delete -----

def test_delete_session(sm):
    session = sm.sessions["Group A"][0]
    assert sm.delete_session(["Group A"], session) is True
    assert [s["name"] for s in sm.sessions["Group A"]] == ["beta"]


def test_delete_session_unknown_returns_false(sm):
    assert sm.delete_session(["Group A"], {"name": "missing"}) is False
    assert sm.delete_session(["Group B"], sm.sessions["Group A"][0]) is False


def test_delete_folder_at_root(sm):
    assert sm.delete_folder(["Group A"]) is True
    assert "Group A" not in sm.sessions


def test_delete_folder_nested(sm):
    assert sm.delete_folder(["Group B", "Sub-1"]) is True
    assert "Sub-1" not in sm.sessions["Group B"]


def test_delete_folder_refuses_root(sm):
    assert sm.delete_folder([]) is False


# ----- duplicate_folder -----

def test_duplicate_folder_inserts_after_original(sm):
    keys_before = list(sm.sessions.keys())
    new = sm.duplicate_folder(["Group A"])
    assert new == "Group A (copy)"
    keys_after = list(sm.sessions.keys())
    # Original at same index, copy right after.
    src_idx = keys_after.index("Group A")
    assert keys_after[src_idx + 1] == "Group A (copy)"
    # Deep copy — mutating the copy doesn't touch the original.
    sm.sessions["Group A (copy)"][0]["name"] = "mutated"
    assert sm.sessions["Group A"][0]["name"] == "alpha"
    # Ordering of unrelated keys is preserved.
    assert [k for k in keys_after if k != "Group A (copy)"] == keys_before


# ----- duplicate_session -----

def test_duplicate_session_inserts_after_original(sm):
    session = sm.sessions["Group A"][0]
    clone = sm.duplicate_session(["Group A"], session)
    assert clone is not None
    assert clone["name"] == "alpha (copy)"
    names = [s["name"] for s in sm.sessions["Group A"]]
    assert names == ["alpha", "alpha (copy)", "beta"]

def test_duplicate_session_uniquifies_when_copy_exists(sm):
    session = sm.sessions["Group A"][0]
    sm.duplicate_session(["Group A"], session)
    second = sm.duplicate_session(["Group A"], session)
    assert second["name"] == "alpha (copy) (2)"
