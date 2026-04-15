# Character Card Guide

The `character` dict on each agent is free-form — the engine never reads it. It becomes the agent's SOUL.md, which defines who they are and how they behave. A good character card is the difference between a boring chatbot and a compelling autonomous agent.

## Recommended Structure

```yaml
character:
  personality: ""        # Core trait in 1-2 sentences. Be specific, not generic.
  goals:                 # What drives this agent. List 2-3 concrete goals.
    - ""
    - ""
  knowledge: ""          # What this agent knows that others don't.
  speaking_style: ""     # How they talk. Dialect, vocabulary, rhythm.
  secret: ""             # Hidden motivation. Creates dramatic tension.
```

These keys are RECOMMENDED, not required. Add any other keys that make sense for the scenario.

## Good Keys to Consider

| Key | Purpose | Example |
|-----|---------|---------|
| `personality` | Core behavioral driver | "Paranoid, resourceful, self-preserving. Trusts no one." |
| `goals` | Concrete objectives (not vague values) | ["Fix the generator", "Find the hidden exit"] |
| `knowledge` | Information asymmetry | "Knows the door code is 4817 but won't share it." |
| `speaking_style` | Voice and tone | "Short, clipped sentences. Military jargon." |
| `secret` | Hidden motivation | "Plans to escape alone if food runs below 5." |
| `backstory` | Context for decisions | "Former engineer. Lost family in the collapse." |
| `relationships` | Feelings toward other agents | "Trusts mei. Suspects ko is hiding food." |
| `weaknesses` | Flaws that create drama | "Cannot resist gambling. Will bet even when losing." |
| `thinking_guide` | Decision-making framework | "Always calculate pot odds before betting." |
| `emotional_triggers` | What makes them react | "Loses composure when accused of lying." |
| `leverage` | Info this agent has over others | "Knows Barrymore stole the aconite." |
| `fears` | What threatens this agent | "If Laura talks to Mortimer, they'll connect me to both crimes." |
| `endgame` | What state this agent needs at the end | "Holmes must believe I was manipulated, not acting independently." |
| `alliances` | Potential allies and conditions | "Laura is useful IF she doesn't realize I manipulated her too." |

## DND-Inspired Extended Structure

For rich RPG-style characters, borrow from D&D character sheets:

```yaml
character:
  # Identity
  personality: "Chaotic good ranger. Distrusts authority, protects the weak."
  backstory: "Grew up in the borderlands. Lost her village to raiders at 14."

  # Stats (flavor, not mechanical — the engine doesn't enforce these)
  strengths: ["tracking", "archery", "wilderness survival"]
  weaknesses: ["social situations", "trusting strangers", "claustrophobia"]

  # Personality traits (D&D style)
  trait: "I always have a plan for what to do when things go wrong."
  ideal: "Freedom. Everyone should be free to choose their own path."
  bond: "I will do anything to protect the people who took me in."
  flaw: "I'd rather eat my own boot than admit I'm wrong."

  # Goals & Secrets
  goals:
    - "Find the source of the blight spreading through the forest"
    - "Protect the village healer at all costs"
  secret: "The blight started after I disturbed the ancient shrine."
  knowledge: "Knows the old forest paths that bypass the main road."

  # Social
  relationships:
    healer: "Protective. Owes her a life debt."
    merchant: "Suspicious. He appeared the same week the blight started."
  speaking_style: "Direct, few words. Uses nature metaphors. Doesn't explain herself."
```

## Goal Design

Goals determine how long agents stay active. A goal that can be completed mid-game produces an agent that goes idle for the rest of the run.

**Wrong — completable goal:**
```yaml
goals:
  - "Destroy the letter"        # Done at tick 10. Agent idles for 40 ticks.
  - "Sink the wire in the mire" # Done at tick 18. Nothing left to do.
```

**Right — verdict/state goal that lasts until the end:**
```yaml
goals:
  - "At dawn the judge delivers a verdict. You must be CLEARED."
  - "Survive until dawn without being connected to the crime."
```

The difference: "destroy the letter" has a completion point. "Be cleared at dawn" never completes — because you can never be sure what Holmes knows, what others have told him, or what evidence has surfaced. The agent must keep monitoring, managing relationships, and reacting until the final tick.

Evidence disposal, information gathering, and social manipulation are all MEANS toward the verdict goal, not goals themselves. When evidence disposal is the goal, agents dispose and stop. When the verdict is the goal, agents dispose early and then spend 30+ ticks managing the people who know what they did.

**Test:** For each agent's primary goal, ask "at what tick could this be done?" If the answer is anything other than "the last tick," the goal needs redesign.

## Common Mistakes

**Too vague:**
```yaml
# BAD — could be anyone
character:
  personality: "Kind and helpful"
  goals: ["Help others"]
```

**Too passive:**
```yaml
# BAD — no drive to ACT
character:
  personality: "Quiet observer who watches everything"
  goals: ["Understand the situation"]
```

**No conflict:**
```yaml
# BAD — will just agree with everyone
character:
  personality: "Team player who values harmony"
  goals: ["Keep everyone happy"]
```

**Good:**
```yaml
# GOOD — specific, active, conflicted
character:
  personality: "Practical engineer. Takes charge. Hates waste."
  goals:
    - "Fix the generator — it's the priority"
    - "Find the hidden exit behind the radio"
  knowledge: "Found a note suggesting there's an escape route."
  speaking_style: "Short, direct. Gives orders. Doesn't waste words."
  secret: "Will abandon the group if the door breaks."
  weaknesses: ["Cannot delegate. Does everything himself."]
```

## Playbook — Teaching Agents How to Operate

Character cards define who the agent IS. But agents also need to know **how to operate in this specific engine** — what actions to use, when, and what to do when they have no actions.

Add a `playbook` key to the character card. This goes into SOUL.md alongside personality and goals, but serves a different purpose: it's an **operating manual**, not identity.

```yaml
character:
  personality: "..."
  goals: [...]
  playbook: |
    [Night] When you see wolf_kill in your actions, pick a target. No actions = not your turn, wait silently.
    [Day] When you see speak in your actions, give your speech. Otherwise wait for your turn.
    [Vote] When you see vote, cast your vote.
    [Important] If you have no available actions, do NOT send any messages. Wait quietly.
```

### When playbooks are essential

- **Turn-based games** — agents must know "no actions = not your turn, wait silently"
- **Role-specific actions** — agents must know which actions are theirs (wolf_kill for wolves, seer_check for seer)
- **Moderator agents** — must know the full flow and when to use each moderator action
- **Phase-dependent behavior** — agents must know what to do in each phase

### Playbook vs Character

| | Character (personality, goals, secret) | Playbook |
|---|---|---|
| Purpose | Who you are | How to play |
| Content | Identity, motivation, knowledge | Actions, phases, procedures |
| Without it | Agent has no personality | Agent doesn't know what to do |
| Example | "Paranoid, distrusts everyone" | "Night: use seer_check. Day: speak when called." |

### Moderator playbooks

If the scenario has a moderator/god agent, its playbook is the most critical. It must cover:
1. The complete flow (what phases exist, in what order)
2. When to use each moderator action
3. **What to check before advancing** (though this should also be enforced by preconditions)

**Rule: never rely solely on a moderator's playbook for flow control.** Always back it up with preconditions on moderator actions. The playbook guides intent; preconditions enforce correctness.

## Key Principles

1. **Goals must reference concrete actions.** "Value teamwork" does nothing. "Patrol between storage and hallway every few ticks" drives behavior.
2. **At least one secret per agent.** Secrets create information asymmetry — the cheapest source of drama.
3. **Internal contradiction.** An agent who wants to help the group BUT also has a selfish goal produces unpredictable, interesting behavior.
4. **Speaking style matters.** Agents that sound different are more compelling. A military engineer and a nervous doctor should not talk the same way.
5. **Knowledge creates power.** An agent who knows something others don't has leverage. This drives negotiation, deception, and revelation.
6. **Playbook for structured scenarios.** If the scenario has turns, phases, or role-specific actions, every agent needs a playbook that teaches them how to operate. Without it, agents will act randomly or spam chat when they should be waiting.
7. **3 agents is the social scenario sweet spot.** With 5 agents, participation drops to ~60%. With 3, every agent participates because their individual contribution visibly matters. Scale up only when the scenario structurally requires more roles.

## Drives Anti-Patterns (Tested Across 65+ Runs)

These patterns were identified through extensive testing. They look reasonable but produce bad results.

### Drives as Instructions (the #1 mistake)

**Wrong — instruction:**
```yaml
drives:
  - "You WILL steal the money"
  - "DEPLOY this information at tick 3"
  - "Side with Riley to repeal quiet hours"
```

**Right — dilemma with competing pressures:**
```yaml
drives:
  - "You have a signed $80K contract waiting — walking away is rational. But the CTO knows your partner from grad school. Burning this bridge could follow you."
  - "The debt is $25K. An equal split gives you $33K — only $8K margin. Stealing guarantees $50K. But if multiple people steal, everyone gets less."
```

LLMs follow instructions. If a drive says "steal", the agent steals. If a drive presents three competing pressures pulling in different directions, the agent weighs them differently each run — producing genuine per-run variety.

**Rule: every key decision point needs at least 2-3 forces pulling in DIFFERENT directions.** One strong pressure = deterministic behavior. Three competing pressures = emergent variety.

### Cross-Agent Secret Leaks

**Wrong — Agent A's drives contain Agent B's secret:**
```yaml
# Agent A (retiree) drives:
drives:
  - "The Parent has a brother named Marcus who was falsely accused. Use this to persuade them."
  # ↑ Marcus is in the Parent's SECRET. Retiree shouldn't know this.
```

**Right — Agent A discovers through gameplay:**
```yaml
drives:
  - "Press on the Parent's hesitation. Ask: 'Have you ever seen someone falsely accused?' If they share something personal, USE it."
```

Drives should contain only information the agent would plausibly have. If Agent A needs to know Agent B's secret, design a mechanism for discovery (investigation, confrontation, evidence), not a drive that leaks it.

### The Confirmation Spectrum

How much certainty to give agents about hidden information:

| Level | Example | Effect |
|-------|---------|--------|
| **Too certain** | "Alex signed a contract with TechCorp" | All agents react the same way (deterministic) |
| **Sweet spot** | "You heard a RUMOR that Alex might be talking to TechCorp" | Creates suspicion without certainty — agents probe, bluff, test |
| **Too vague** | "Something might be going on with Alex" | Agents ignore it (not actionable) |

One confirmed fact > ten vague hints. But TOO confirmed = everyone reacts identically = no variety. The sweet spot is a **rumor or partial information** that agents can investigate, deploy strategically, or ignore.

### LLM Argument Counting

LLMs count arguments, not argument strength. If the prosecution has 5 talking points and the defense has 3, agents default to prosecution — even if the defense points are individually stronger. **Balance the COUNT of arguments on each side**, not just the overall strength.
