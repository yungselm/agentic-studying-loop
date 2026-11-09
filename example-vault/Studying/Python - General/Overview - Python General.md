---
type: overview
---
# Python (general): study notes

> [!tldr]
> Python ideas that came up across projects. Start top left on the map.

```mermaid
flowchart LR
    TF[try - finally] -->|builds on| CM[Context managers]
    CM -->|used by| AW[Atomic file writes]
    class TF,CM,AW internal-link
```

## Reading order
1. [[try - finally]]: cleanup that runs on every exit path
2. [[Context managers]]: what `with` calls, in which order, and when errors are swallowed
