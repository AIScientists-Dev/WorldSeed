# Scenario Architecture

Runtime makes the agents run. Scenario architecture makes the run interesting.

Do not design a pipeline. Design pressure.

```text
roles + private information + goals + actions + consequences + artifact history
=> emergence
```

## Core Shape

A strong WorldSeed scene has these parts:

```text
roles              who acts
private info       what each role knows or cares about
goals              what each role tries to protect or win
actions            what agents can do to the world
consequences       who gets woken, blocked, pressured, or rewarded
artifact history   what remains visible after the run
```

If the scene only says "producer writes, critic critiques, curator selects",
it will behave like a normal multi-agent pipeline.

## Make Roles Pull In Different Directions

Roles should create pressure, not just divide labor.

Examples:

```text
builder      wants its branch to survive
critic       wants to reject boring or unsupported work
audience     protects attention and clarity
technical    protects reproducibility
curator      must ship and justify the final package
```

The point is not conflict for drama. The point is better artifacts through
different incentives.

## Use Private Information

Do not give every agent the same view.

Examples:

```text
API explorer sees constraints and failure modes
prompt miner sees patterns and anti-patterns
audience sees usefulness and confusion
technical judge sees reproducibility risks
curator sees the whole artifact graph
```

Asymmetry is what makes agents disagree for real reasons.

## Actions Must Change The Situation

An action should not only record text. It should change what happens next.

Examples:

```text
submit_version      creates a candidate and wakes judges
critique_artifact   attaches pressure to one exact artifact and wakes owner
select_branch       changes artifact status and wakes owner
submit_package      closes a run with cited evidence
```

If actions do not create consequences, the scene becomes a shared folder.

## Keep Artifact History

Emergence should be inspectable after the run.

Use append-only records for:

```text
attempts
versions
critiques
rebuttals
revision requests
selections
final packages
```

Final output should cite exact artifact ids, including rejected or revised
branches. The trail is part of the product.

## Let MAIN Steer, Not Script

The primary session should not pre-write the whole flow.

It should:

```text
start with enough structure
spawn parallel branches when useful
read signals and artifact ids
wake agents when consequences require reaction
increase pressure when outputs are generic
stop when the artifact graph is strong enough
```

Good runs feel designed at the rules level, not scripted at the outcome level.

