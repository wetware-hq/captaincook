# `/load` copy (locked)

**Owner:** biolang  
**Note:** User reverted the `/sequence` rename. **`/load` is the primary command.** Do not advertise `/sequence` in HELP or README.

## Commands

| Command | Meaning |
| --- | --- |
| `/load <nl>` | Parse a request into a context card. No computation is started. |
| `/load` | Show the current card. |
| `/load clear` | Discard the card, patient biometrics, and patient files. |

## If `/sequence` is still registered

Prefer removing it from BotFather. If a stub remains temporarily:

```
`/sequence` has been withdrawn. Please use /load with the same arguments.
```
