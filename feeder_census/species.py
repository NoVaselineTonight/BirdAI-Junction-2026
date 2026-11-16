import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

HABITATS = ("forest", "farmland", "town", "generalist")

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "species.toml"


@dataclass(frozen=True)
class Species:
    key: str
    scientific: str
    english: str
    finnish: str
    habitat: str = ""  # pests have none
    core: bool = False
    aliases: tuple[str, ...] = ()


def load_species(path: Path | None = None) -> list[Species]:
    with open(path or _DEFAULT_PATH, "rb") as f:
        rows = tomllib.load(f)["species"]
    return [
        Species(
            key=row["key"],
            scientific=row["scientific"],
            english=row["english"],
            finnish=row["finnish"],
            habitat=row["habitat"],
            core=row["core"],
            aliases=tuple(row.get("aliases", ())),
        )
        for row in rows
    ]


def load_pests(path: Path | None = None) -> list[Species]:
    """The unwanted animals that close the latch. Never census species: `load_species` leaves them out."""
    with open(path or _DEFAULT_PATH, "rb") as f:
        rows = tomllib.load(f).get("pest", [])
    return [
        Species(key=row["key"], scientific=row["scientific"], english=row["english"], finnish=row["finnish"])
        for row in rows
    ]


def habitat_mix(counts: Mapping[str, int], species: Sequence[Species]) -> dict[str, int]:
    """Birds per habitat. Every habitat is present; keys not in `species` are ignored."""
    habitat_of = {s.key: s.habitat for s in species}
    mix = {habitat: 0 for habitat in HABITATS}
    for key, n in counts.items():
        if key in habitat_of:
            mix[habitat_of[key]] += n
    return mix
