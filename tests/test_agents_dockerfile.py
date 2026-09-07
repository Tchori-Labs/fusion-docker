import pathlib
import re


DOCKERFILE = pathlib.Path(__file__).parent.parent / "agents" / "Dockerfile"

# Debian 12 package union required by Playwright 1.61.1 Chromium revision 1228.
EXPECTED_CHROMIUM_DEPS = {
    "libglib2.0-0",
    "libnss3",
    "libnspr4",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libatspi2.0-0",
    "libcups2",
    "libdbus-1-3",
    "libx11-6",
    "libxcomposite1",
    "libxdamage1",
    "libxext6",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libxcb1",
    "libxkbcommon0",
    "libpango-1.0-0",
    "libcairo2",
    "libasound2",
}


def declared_chromium_deps(source):
    match = re.search(
        r'ARG PLAYWRIGHT_CHROMIUM_DEPS="(?P<value>.*?)"',
        source,
        re.DOTALL,
    )
    assert match, "the Playwright Chromium dependency list must remain explicit"
    return match.group("value").replace("\\\n", " ").split()


def test_pins_the_playwright_chromium_dependency_set():
    source = DOCKERFILE.read_text()

    assert "ARG PLAYWRIGHT_VERSION=1.61.1" in source
    assert "ARG PLAYWRIGHT_CHROMIUM_REVISION=1228" in source
    assert set(declared_chromium_deps(source)) == EXPECTED_CHROMIUM_DEPS
    assert len(declared_chromium_deps(source)) == len(EXPECTED_CHROMIUM_DEPS)


def test_installs_dependencies_slimly_as_root_and_returns_to_node():
    source = DOCKERFILE.read_text()
    install = source.index("${PLAYWRIGHT_CHROMIUM_DEPS}")

    assert source.index("USER root") < install
    assert "apt-get install -y --no-install-recommends" in source
    assert "rm -rf /var/lib/apt/lists/*" in source
    assert source.rstrip().endswith("USER node")


def test_image_build_does_not_download_a_project_browser():
    source = DOCKERFILE.read_text().lower()

    assert "playwright install" not in source
    assert "npx playwright" not in source
    assert "playwright install-deps" not in source
