"""Labels and citations in an answer: the rules the eval harness scores and the agent's rewrite checks."""
from backend.agent import coverage, tools
from evals import run_all

IDEAS = tools.fleet_opportunities(site_id="S1")
S3 = tools.fleet_opportunities(site_id="S3")


def test_a_sentence_with_a_figure_needs_its_label_in_the_same_sentence():
    answer = "The fleet used 16,492 litres (allocated). Tractor 4 burned 2,100 litres. No figures here."
    assert coverage.label_coverage(answer) == (1, 2)
    assert coverage.unlabelled_sentences(answer) == ["Tractor 4 burned 2,100 litres."]


def test_an_idea_named_with_one_of_its_sources_is_cited():
    answer = "Shift up / throttle down (Shift Up and Throttle Back to Save Tractor Fuel, strong evidence) could help."
    assert coverage.citation_coverage(answer, [IDEAS]) == (1, 1)
    assert coverage.uncited_ideas(answer, [IDEAS]) == []


def test_an_idea_named_without_a_source_is_listed_with_its_titles():
    answer = "Try no-till on the arable fields."
    assert coverage.citation_coverage(answer, [IDEAS]) == (0, 1)
    [gap] = coverage.uncited_ideas(answer, [IDEAS])
    assert gap["name"] == "No-till" and any("Košutić" in t for t in gap["titles"])


def test_an_idea_shown_for_two_sites_counts_twice_but_is_listed_once():
    answer = "No-till could help at both sites."
    assert coverage.citation_coverage(answer, [IDEAS, S3])[1] == 2
    assert [g["name"] for g in coverage.uncited_ideas(answer, [IDEAS, S3])] == ["No-till"]


def test_the_harness_scores_with_the_same_rules():
    run = {"case_id": None, "question": "q", "answer": "Try no-till. The fleet used 16,492 litres.",
           "tool_calls": [{"name": "fleet_opportunities", "args": {"site_id": "S1"}, "output": IDEAS}]}
    s = run_all.score_run(run)
    assert (s["cited"], s["recommendations_named"]) == (0, 1) and (s["labelled_figures"], s["figures"]) == (0, 1)


def test_figures_with_needless_decimals_are_found_but_rounded_ones_and_prices_are_not():
    assert coverage.unrounded_numbers("Die Flotte hat 16492.14 Liter (allocated), davon 345.55 Liter.") == ["16492.14 Liter", "345.55 Liter"]
    assert coverage.unrounded_numbers("16,492 litres, 16.492 Liter, 29.8 tonnes, £0.80 a litre, £693 to £1,830, 4.1%.") == []
