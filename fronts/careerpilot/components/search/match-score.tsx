// compatibility is qualification_check's 0-10 score.
export function MatchScore({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1 w-14 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-foreground/60" style={{ width: `${score * 10}%` }} />
      </div>
      <span className="text-sm tabular-nums">{score}</span>
    </div>
  )
}
