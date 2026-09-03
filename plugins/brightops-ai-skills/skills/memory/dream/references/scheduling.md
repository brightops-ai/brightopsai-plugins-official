# Running dream on a schedule

## The two-run pattern

The analysing run leaves proposals waiting for a decision. Without a second run,
a problem found on Friday sits unfixed until the next Friday — a full cycle of
knowingly stale memory.

So: one routine runs `full-analysis`, and a second runs `apply-fixes` a day
later, after you have read the overview and ticked what you agree with.

```
day one   dream full-analysis   →  overview written, summary delivered
          (you read it and tick what you agree with)
day two   dream apply-fixes     →  ticked items applied, summary delivered
```

Daily, weekly, or anything else works. The gap matters more than the cadence:
it has to be long enough that you actually read the overview.

## The invocation requirement

**A skill with `disable-model-invocation: true` cannot be fired by a scheduled
task.** The field blocks scheduled invocation as well as automatic loading.

This is why `dream` omits that field while the other skills in this plugin set
it. Scheduling a skill that carries the flag produces a routine that fires and
does nothing, and reports no error — the worst available failure, because it
looks like it is working.

If you fork this skill, keep the field off, or the schedule stops silently.

## Setting it up

Create two scheduled routines through whatever scheduling mechanism your setup
provides, one per mode, referencing the skill by name with its mode argument.

Keep the schedule definition outside this repository. A routine naming a real
machine, path or channel does not belong in a plugin that other people install.

## Before trusting the schedule

Run both modes by hand first, in that order, and confirm:

- the analysing run finds the right memory directory — check `memory_source`
- the overview is delivered somewhere you actually read
- ticking an item causes the applying run to make exactly that change
- restoring a snapshot puts memory back

An unattended run is only as trustworthy as the attended run you checked.
