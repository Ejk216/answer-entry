# Solving: verification and procedures

Read this file in Solve and Check modes. Enter mode doesn't need it.

## Self-verification

When no answer key exists, Claude is the only check on Claude. On Top Hat, correct answers are hidden even after submission, so it is the *only* check ever.

### Protocol

Run all five on every self-derived computational answer:

1. **Substitute back into the original** — not the simplified form.
2. **Domain-check every candidate** (log arguments $>0$, even radicands $\ge 0$, denominators $\ne 0$).
3. **Re-derive by a second route.** One derivation that re-reads itself is worth nothing.
4. **Numeric evaluation** for plausibility.
5. **Count expected solutions.**

For code-output questions ("what is the value of…", "what is printed by…") the second route is **running the code**. Put every expression in the set into one python script and print the results — never reason out `rfind`, slice bounds or a format spec by hand when the interpreter will answer. Print `repr()`, and wrap printed output in markers so leading and trailing spaces are visible, because answer choices often differ only by padding.

Conceptual items (variable types, study design, parameter vs statistic) can't run all five: check against the textbook definition and name any convention the course might set differently.

### Confidence gating

- **Solid** — routes agree / definition unambiguous.
- **Needs review** — anything else: graph interpretation, convention-dependent answers, or a matching item whose "right" option isn't literally offered (then pick the option consistent with the other matches — e.g. population = the group the parameter describes).

Report "needs review" problems **first**, with the doubt named.

## Read the actual problem

WeBWorK randomizes values per student; Top Hat may pre-shuffle drag-and-drop options. Always read the rendered statement and the widget's current state.

## Solution procedures

### Inequalities (test-point method)

1. One side vs $0$. **Never cross-multiply by a variable expression.**
2. Boundaries = numerator zeros **and** denominator zeros.
3. Test one point per interval **numerically in the original**; don't assume signs alternate (even-multiplicity roots).
4. Include numerator zeros only for $\le$/$\ge$; **never** include undefined points. Cancelled factors are still holes.

### Logarithmic and exponential equations

Combine, exponentiate, domain-check every candidate — extraneous roots are the norm. $a^{x}=b \Rightarrow x=\frac{\ln b}{\ln a}$, left exact.

### Absolute value

$|A|=c$: $A=\pm c$ (none if $c<0$). $|A|<c \Rightarrow -c<A<c$; $|A|>c \Rightarrow A<-c$ or $A>c$.

### Inverse functions

Swap and solve; a restricted domain picks the branch. Domain of $f^{-1}$ = range of $f$.

### Trigonometry

Reference angle + quadrant sign, rationalized. Find **every** solution in the interval.

### Simplification and domain

Identities hold only where the *original* was defined.

### Graph identification

Match on intercept, asymptote, domain — not overall shape.

### Intro programming (strings, slicing, formatting)

Run it rather than reason it. Traps worth recognising anyway:

- `3 * "125"` repeats the string; `3 * int("125")` is arithmetic; `3 * str(125)` repeats again.
- `in` on strings tests **substring**, not "any of these letters" — `"ad" in "aardvark"` is `False`.
- Negative slices: `Z[-3:]`, `Z[-6:-2]` — count from the end, stop index exclusive.
- String comparison is codepoint-wise, so every uppercase letter sorts before every lowercase one: `"Tiger" > "tiger"` is `False`. Length only decides when one string is a prefix of the other — `"ants" < "anteater"` is `False`, because the first difference (`s` vs `e`) settles it.
- `find` gives the first index, `rfind` the last, `-1` when absent; `count` counts non-overlapping occurrences.
- Format specs: width pads, `>`/`<` set alignment, `+` forces a sign. `{:.4f}` on a denormal prints `0.0000`; `{:.4f}` on a near-max float prints all 300+ digits, while `{:.4e}` stays compact.

### Statistics courses

- **Decimals to stated precision; carry full precision, round only at the end.**
- **Carry-through parts:** solve chained parts as one computation.
- **Variable types:** yes/no or labels → nominal; ordered categories (low/medium/high, education level) → ordinal; measured or counted quantities → numerical. A sample size, a study's headline result ("42% lower risk"), or other single study-level number is **not a variable**.
- **Parameter vs statistic:** known population value → parameter; value computed from the sample → statistic.
- **Two-way tables:** marginal = row/col total ÷ grand total; joint = cell ÷ grand total; conditional = cell ÷ the *given* row/col total. **Base-rate / diagnostic tables** on a hypothetical 10,000: diseased = rate×10,000; TP = sensitivity×diseased; TN = specificity×healthy; fill the rest by subtraction. Enter unrounded cell values (e.g. 536.79). Raising the base rate raises P(disease | positive).
- **Mosaic plots:** column **width** = that variable's marginal share (widest = most entries); segment **height within a column** = conditional share. Pick the plot whose columns are the variable you're conditioning on.
- **Boxplots:** read Q1/median/Q3/whiskers/outliers per group; "proportion above x" follows from where x falls (above Q3 → <25%, above median → <50%). Match an unlabeled histogram to a group by its **min/max range and outliers** first, then peak location.
- **SD vs a benchmark:** compare the benchmark with roughly range/4–range/6 of the bulk.
- **Adding one value:** mean falls iff value < mean; recompute median as the new middle; SD rises iff |value − mean| is large relative to SD — just compute all candidates in python.
- **Paired data:** mean of differences = difference of means; SD of differences ≠ difference of SDs.
- **Shape and center:** the mean is pulled toward the long tail. "Symmetric" includes multimodal mirror-image shapes.
- **Spread from dot plots:** all points at one value = zero; mass at both extremes = most.
- **Confounders** must plausibly relate to both explanatory and response variables.
