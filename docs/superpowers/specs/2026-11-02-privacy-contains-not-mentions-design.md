# Privacy score: "contains", not "mentions"

Date: 2026-11-02 · Status: draft for review

## Why

Verdict AI's risk score can't tell a victim from a violator. The review
"They posted my email address in public." scores **High (0.80)**. It's a
legitimate review written by the person whose information was exposed, and it
should stay up.

What actually happens today (measured with default settings: 60% policy
weight, 5 similar cases):

- `RULE_PRIVACY` matches the **keyword** `email address`. No email address
  appears in the text. The keyword alone adds the rule's full weight, 0.80.
- `RuleEngine.decide` sets `final_score = max(rule_score, weighted_score)`
  (`app/decision.py:126`), so one rule at 0.80 clears the 0.70 High line by
  itself. Similarity (0.55 here) is blended in, then discarded by the `max`.
- Separately, the similarity signal is unsound. It is the average closeness of
  the top-k samples and ignores their labels. The sample set
  (`data/samples/sample_reviews.csv`, 20 rows) contains this exact review,
  labelled 7 (Privacy Violation). Victim reports like "Home address was leaked
  in their reply." are labelled as violations too. The labels aren't verified
  outcomes, and we've seen some are wrong.

## Goals

1. A review gets the privacy score only when it **contains** personal
   information, not when it **talks about** it.
2. A review that mentions personal information but contains none scores Low
   on privacy, and the result says so in plain words:
   *"Mentions personal information (email address) but doesn't contain any."*
3. The risk score comes from the policy rules alone. Similar cases stay on
   screen as context only.
4. What the score explanation says is exactly what the code computes.

## Non-goals

- The victim-or-violator problem in other rules, especially toxic. See
  Follow-ups.
- Learning from outcomes, or recalibrating similarity. That waits until real,
  verified outcomes exist.
- New kinds of personal-info detection (names, street addresses, license
  plates as text patterns).

## Anti-goals (would make this a failure even if it "works")

- A review that contains a real email address, phone number or SSN scores
  lower than High, even when the writer is the victim. The exposure itself is
  the harm.
- A resident mentioning their own unit ("I live in 4B and the leak wasn't
  fixed for months") gets a privacy score.
- The screen still shows a "similarity contribution", or a slider that
  suggests similarity could count.
- A mention-only review drops to Low with no explanation, so it looks as if
  the privacy rule never checked it.

## Decisions (made by the product owner)

### Privacy rule

- **Counts as containing personal info:** an email address
  (`name@example.com`), a phone number (`555-123-4567`), a Social Security
  number (`123-45-6789`). These come from `RULE_PRIVACY`'s existing pattern.
- **Does not count:** a unit, apartment or room number on its own. Remove the
  `(apt|unit|room)\s?#?\d+` part of the pattern.
- **Mention-only phrases:** `email address`, `home address` and `full name`
  (and the other phrases that name a kind of personal info, see "Builder's
  calls") no longer score. When one matches and the pattern finds nothing, the
  privacy rule scores 0 and carries the mention-only explanation above, naming
  the phrase(s) it saw.
- When real personal info is present, the rule fires as today (0.80, or 1.0
  with "strong evidence" on), whether or not a mention phrase is also present.

### Similarity

- Context only. It must not raise or lower the score until there are verified
  outcomes.
- Similar cases stay in the "Similar Cases" panel as they are now.
- Remove the "Policy signal weight" slider. With similarity out of the score
  there is nothing left for it to balance.
- Remove the "Sample cases: … × …% weight = … points" line from "How scoring
  works → Technical details". Say instead that similar cases are shown for
  comparison and don't affect the score.

### Promotion rule's ".com" problem

`RULE_PROMOTION`'s pattern matches `\.com\b` and a full email regex. A leaked
email ("They posted my full name and email@example.com.") therefore also gets
flagged as **promotion**, which gives a misleading explanation. Fix it so
contact details on their own (an email address, or a phone number, which the
pattern also matches) don't count as promotion. Links and calls to action
still do.

### Scoring bugs fixed along the way

- The multi-rule bonus (`+0.10` per extra triggered rule, cap 0.95) is
  computed and then overwritten (`app/decision.py:121-126`), but the screen
  says it applies. Make it apply.
- `analyze_review_text`'s strong-evidence path (`streamlit_app.py:174`)
  recalculates the score with its own copy of the formula and leaves the stored
  `result["risk_level"]` stale. The visible label is unaffected, because the UI
  re-derives it with `apply_thresholds`. There should be one scoring formula,
  used everywhere, and no stale fields.

### "Strong evidence" defaults to off

With similarity out of the score, "Treat detected text patterns as strong
evidence" would push every pattern match to 1.0, so every match would show
95% High. The score would stop telling cases apart, and ordinary complaints
("Covid rules are unclear; mask mandate not enforced.") would be treated like
real violations. Change the default of `strong_evidence` to **off**. Each rule
then scores its own weight: toxic 85%, privacy 80%, promotion 70%, COVID 65%.
The checkbox stays available in the demo controls.

## Resulting score (the builder's formula to implement)

```
rule_score  = min(1.0, sum of triggered rule scores)
final_score = min(0.95, rule_score + 0.10 × max(0, triggered_rules − 1))
```

Tiers use the existing High/Medium threshold sliders (`apply_thresholds`).
`neighbor_conf` is still computed for the panel, and is never an input to
`final_score`.

## Expected outcomes (acceptance checks)

| Review | Privacy | Promotion | Overall |
|---|---|---|---|
| They posted my email address in public. | 0, mention note ("email address") | — | Low |
| Home address was leaked in their reply. | 0, mention note ("home address") | — | Low |
| They posted my full name and email@example.com. | fires (email) | does **not** fire | High |
| They shared my unit 302 and phone 555-123-4567. | fires (phone, not unit) | does **not** fire | High |
| I live in 4B and the leak wasn't fixed for months. | 0, no note | — | Low |
| Limited time offer! Apply now and schedule a tour. Call us today. | — | fires | High (unchanged) |

The table assumes the new defaults (strong evidence off, High ≥ 0.70,
Medium ≥ 0.40). Other sample reviews may change tier, because similarity no
longer counts, strong evidence is off, and the multi-rule bonus now applies.
That is expected, not a failure. The builder lists each sample's old and new
score and tier in the PR so the changes can be reviewed.

## Constraints

- Streamlit prototype, 20 sample reviews, no verified outcomes, no test suite
  today. CI runs SonarQube only.
- Don't change the sample labels in this work. They're shown as "Sample
  label", and they're context only now.
- Keep the queue's risk badges and the Moderation panel on the same scoring
  path (`analyze_review_text`). Drop `alpha_key` from the queue cache key.

## Builder's calls (decided by Claude, open to change)

- **Phone formats.** Promotion's pattern currently catches phone numbers with
  dots or no separators (`415.555.0199`, `4155550199`), and privacy's only
  catches dashes. Once promotion drops phones, widen the privacy phone pattern
  to the same `\b\d{3}[-.]?\d{3}[-.]?\d{4}\b`. Otherwise those leaks would
  fall to Low. This is the same kind of detection the app already does, not a
  new one.
- **"Always High" holds at the default thresholds.** The threshold sliders
  are demo controls. A moderator who raises High above 0.80 with strong
  evidence off will see a lone email as Medium, and that's intended. No floor
  or override.
- **Other privacy keywords.** Keywords that name a kind of personal info
  (`private info`, `personal info`, `personal information`,
  `private information`, `share address`, `shared phone number`,
  `social security`, `ssn`, `license plate`, `leaked info`) become
  mention-only like the three above. The pattern's
  `\b(ssn|social security)\b` alternative is a mention too, so remove it from
  the pattern. `final walk`, `vacate apartment` and `bh management` are
  word-statistics artifacts, not mentions of personal info. Remove them from
  the privacy rule.
- **Where the mention note shows.** In the privacy rule's entry under the
  result's policy signals, styled as information (not a warning), with the
  mentioned phrase highlighted in the review the way matched phrases are
  today. It doesn't count as a "policy signal matched".
- **Promotion fix shape.** Drop the email and phone alternatives from the
  promotion pattern, and stop `.com`/`.net`/`.ru` from matching inside an
  email address. "Call us", "contact us" and the like keep promotion firing
  when contact details come with a call to action.
- **`RuleEngine`'s `alpha`.** Remove it, along with `alpha`/`beta` in the
  result, rather than pinning it to 1.0.
- **Checks.** Add a small pytest file covering the expected-outcomes table
  above, calling `RuleEngine` directly, with no Streamlit or embedding model.

## Left to the builder

Code structure, exact copy beyond the mention note, and how the
"How scoring works" text is reworded, provided it stays true to the formula.

## Follow-ups (not in this design)

- **Victim reports in the toxic rule.** "Pervert keeps harassing residents in
  the gym" is a report of harassment, but the word "harassing" scores it as
  toxic. This is harder than privacy: there's no clear marker like an actual
  email address. And that example isn't clean anyway, because "pervert" is
  itself an insult.
- **Sample set quality.** Victim reports are labelled as violations, and the
  demo review is itself one of the 20 samples (it matches itself at 1.00).
  Revisit before similarity is ever allowed back into the score.
