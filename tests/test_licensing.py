from forage.licensing import parse_license


def test_license_variants():
    cases = {
        "http://creativecommons.org/publicdomain/zero/1.0/": ("CC0", False, False, False, False),
        "https://creativecommons.org/licenses/by/4.0/": ("CC-BY", True, False, False, False),
        "http://creativecommons.org/licenses/by-nc/3.0/": ("CC-BY-NC", True, True, False, False),
        "http://creativecommons.org/licenses/by-nc-sa/3.0/": ("CC-BY-NC-SA", True, True, True, False),
        "http://creativecommons.org/licenses/by-nc-nd/4.0/": ("CC-BY-NC-ND", True, True, False, True),
        "http://creativecommons.org/licenses/by-sa/3.0/": ("CC-BY-SA", True, False, True, False),
        "http://creativecommons.org/licenses/by-nd/4.0/": ("CC-BY-ND", True, False, False, True),
        "https://creativecommons.org/licenses/sampling+/1.0/": ("Sampling+", True, False, False, False),
        None: ("Unknown", False, False, False, False),
    }
    for url, (name, ra, nc, sa, nd) in cases.items():
        f = parse_license(url)
        assert f["license_name"] == name
        assert (f["requires_attribution"], f["non_commercial"], f["share_alike"], f["no_derivatives"]) == (ra, nc, sa, nd)
