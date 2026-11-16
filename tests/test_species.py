from feeder_census.species import HABITATS, habitat_mix, load_species


def test_core_species_are_the_sketch_eight():
    sp = load_species()
    assert [s.key for s in sp if s.core] == [
        "great_tit", "yellowhammer", "blue_tit", "tree_sparrow",
        "bullfinch", "blackbird", "greenfinch", "house_sparrow"]
    assert len({s.key for s in sp}) == len(sp) == 22
    assert all(s.finnish and s.habitat in HABITATS for s in sp)


def test_habitat_mix_adds_birds_per_habitat():
    mix = habitat_mix({"willow_tit": 2, "bullfinch": 3, "house_sparrow": 4, "great_tit": 5}, load_species())
    assert mix == {"forest": 5, "farmland": 0, "town": 4, "generalist": 5}


def test_pests_load_and_are_not_census_species():
    from feeder_census.species import load_pests

    pests = load_pests()
    assert [(p.key, p.english, p.finnish, p.scientific) for p in pests] == [
        ("red_squirrel", "Red squirrel", "Orava", "Sciurus vulgaris"),
        ("brown_rat", "Brown rat", "Rotta", "Rattus norvegicus")]
    assert all(p.habitat == "" and p.core is False and p.aliases == () for p in pests)
    assert not {p.key for p in pests} & {s.key for s in load_species()}
