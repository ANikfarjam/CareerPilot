"use client"

import { useState, type FormEvent, type ReactNode } from "react"
import { Briefcase, Globe, LoaderCircle, Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable"
import { useIsMobile } from "@/hooks/use-mobile"
import { addPortal, addTargetPosition, removePortal, removeTargetPosition } from "@/lib/api"

import { errorMessage, titleCase } from "./format"

type Props = {
  portals: string[]
  positions: string[]
  onPortalsChange: (portals: string[]) => void
  onPositionsChange: (positions: string[]) => void
  locked: boolean // portals.yml can't be edited during an agent run
}

// The panel's own wrapper scrolls by default (inline overflow: auto); only the list should.
const PANEL_STYLE = { overflow: "hidden", height: "100%" } as const

// Overview tab: the portals and target positions from portals.yml, side by side in resizable panels.
export function OverviewTab({ portals, positions, onPortalsChange, onPositionsChange, locked }: Props) {
  const isMobile = useIsMobile()

  return (
    <div className="space-y-3">
      {locked && (
        <p className="text-sm text-muted-foreground">An agent run is in progress; editing is paused until it finishes.</p>
      )}
      {/* Fixed height: each panel's list scrolls inside it instead of growing the page. */}
      <div className="h-[640px] overflow-hidden rounded-xl border bg-card md:h-[520px]">
        <ResizablePanelGroup orientation={isMobile ? "vertical" : "horizontal"} className="h-full">
          <ResizablePanel defaultSize="50%" minSize="25%" style={PANEL_STYLE}>
            <PortalsPanel portals={portals} onChange={onPortalsChange} locked={locked} />
          </ResizablePanel>
          <ResizableHandle withHandle />
          <ResizablePanel defaultSize="50%" minSize="25%" style={PANEL_STYLE}>
            <PositionsPanel positions={positions} onChange={onPositionsChange} locked={locked} />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  )
}

function PortalsPanel({ portals, onChange, locked }: { portals: string[]; onChange: (p: string[]) => void; locked: boolean }) {
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")

  return (
    <EditableList
      title="Portals"
      description="Company career pages the search agent scans."
      icon={<Globe />}
      items={portals}
      empty="No enabled portals. Add a company's careers page above."
      locked={locked}
      canAdd={name.trim() !== "" && /^https?:\/\//.test(url.trim())}
      onAdd={async () => {
        onChange(await addPortal(name.trim(), url.trim()))
        setName("")
        setUrl("")
      }}
      onRemove={async (item) => onChange(await removePortal(item))}
      fields={
        <>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Company" className="sm:w-40" />
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://company.com/careers"
            type="url"
            className="flex-1"
          />
        </>
      }
    />
  )
}

function PositionsPanel({ positions, onChange, locked }: { positions: string[]; onChange: (p: string[]) => void; locked: boolean }) {
  const [keyword, setKeyword] = useState("")

  return (
    <EditableList
      title="Target positions"
      description="Title keywords a posting must match to be kept."
      icon={<Briefcase />}
      items={positions}
      format={titleCase}
      empty="No target positions. Add a title keyword above."
      locked={locked}
      canAdd={keyword.trim() !== ""}
      onAdd={async () => {
        onChange(await addTargetPosition(keyword.trim()))
        setKeyword("")
      }}
      onRemove={async (item) => onChange(await removeTargetPosition(item))}
      fields={
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="e.g. machine learning engineer"
          className="flex-1"
        />
      }
    />
  )
}

type EditableListProps = {
  title: string
  description: string
  icon: ReactNode
  items: string[]
  format?: (item: string) => string
  empty: string
  locked: boolean
  fields: ReactNode // inputs of the add form
  canAdd: boolean
  onAdd: () => Promise<void>
  onRemove: (item: string) => Promise<void>
}

// A titled list with an add form on top and a delete button on each row (both panels use it).
function EditableList({ title, description, icon, items, format, empty, locked, fields, canAdd, onAdd, onRemove }: EditableListProps) {
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setAdding(true)
    setError(null)
    try {
      await onAdd()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setAdding(false)
    }
  }

  const remove = async (item: string) => {
    setRemoving(item)
    setError(null)
    try {
      await onRemove(item)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 font-medium [&_svg]:size-4 [&_svg]:text-muted-foreground">
              {icon}
              {title}
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          </div>
          <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium tabular-nums text-muted-foreground">
            {items.length}
          </span>
        </div>
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
          {fields}
          <Button type="submit" variant="outline" disabled={locked || adding || !canAdd}>
            {adding ? <LoaderCircle className="animate-spin" /> : <Plus />}
            Add
          </Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {items.length === 0 ? (
        <p className="p-6 text-center text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="min-h-0 flex-1 divide-y overflow-y-auto overscroll-contain">
          {items.map((item) => (
            <li key={item} className="group flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-muted/40">
              <span className="truncate">{format ? format(item) : item}</span>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Remove ${item}`}
                disabled={locked || removing !== null}
                onClick={() => remove(item)}
                className="text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 hover:text-destructive max-md:opacity-100"
              >
                {removing === item ? <LoaderCircle className="animate-spin" /> : <Trash2 />}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
