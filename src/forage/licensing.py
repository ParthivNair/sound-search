"""Map a Freesound license URL to a canonical name + obligation flags.

The user's direction: fetch broadly across CC, but capture every obligation per
sound and surface it at use time. So we never block on license here — we record
what the producer must honor (attribution / non-commercial / share-alike /
no-derivatives) and let search/credits surface it.
"""

from __future__ import annotations


def parse_license(url: str | None) -> dict:
    """Order matters: most-specific variants are matched first."""
    u = (url or "").lower()
    f = {
        "license_url": url,
        "requires_attribution": False,
        "non_commercial": False,
        "share_alike": False,
        "no_derivatives": False,
    }
    if "publicdomain/zero" in u or "/cc0" in u:
        name = "CC0"
    elif "by-nc-sa" in u:
        name = "CC-BY-NC-SA"; f.update(requires_attribution=True, non_commercial=True, share_alike=True)
    elif "by-nc-nd" in u:
        name = "CC-BY-NC-ND"; f.update(requires_attribution=True, non_commercial=True, no_derivatives=True)
    elif "by-nc" in u:
        name = "CC-BY-NC"; f.update(requires_attribution=True, non_commercial=True)
    elif "by-sa" in u:
        name = "CC-BY-SA"; f.update(requires_attribution=True, share_alike=True)
    elif "by-nd" in u:
        name = "CC-BY-ND"; f.update(requires_attribution=True, no_derivatives=True)
    elif "/by/" in u or u.rstrip("/").endswith("/by"):
        name = "CC-BY"; f.update(requires_attribution=True)
    elif "sampling+" in u or "samplingplus" in u:
        name = "Sampling+"; f.update(requires_attribution=True)
    else:
        name = "Unknown"
    f["license_name"] = name
    return f


def attribution_line(meta: dict) -> str:
    """One-line credit string. Falls back gracefully when fields are missing."""
    who = meta.get("attribution_username") or "creator unknown"
    link = meta.get("attribution_url") or meta.get("license_url") or "(no link)"
    return f"Credit {who} ({link})"


def obligations(meta: dict) -> list[str]:
    """Human-readable 'what the producer must do', driven by the license name +
    the four obligation flags. Used by `forage credits` to render the manifest."""
    name = meta.get("license_name") or "Unknown"
    if name == "CC0":
        return ["No obligation — public-domain dedication (CC0). Credit appreciated, not required."]
    if name == "Unknown":
        return ["⚠ License unknown — verify terms before release; treat as all-rights-reserved until confirmed."]
    out: list[str] = []
    if meta.get("requires_attribution"):
        out.append(f"{attribution_line(meta)} — attribution required.")
    if meta.get("non_commercial"):
        out.append("⚠ Non-commercial only — not for paid/commercial releases.")
    if meta.get("no_derivatives"):
        out.append("⚠ No derivatives — may not be modified/transformed.")
    if meta.get("share_alike"):
        out.append("Share-alike — derivatives must use the same license.")
    if not out:  # recognized name but no flags set
        out.append(f"See the {name} terms before release.")
    return out
