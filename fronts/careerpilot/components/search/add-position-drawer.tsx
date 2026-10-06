"use client"

import { useState, type FormEvent } from "react"
import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { JobType, ManualPosition } from "@/lib/api"

import { titleCase } from "./format"

const JOB_TYPES: JobType[] = ["onsite", "hybrid", "remote", "unknown"]
const JOB_TYPE_ITEMS = Object.fromEntries(JOB_TYPES.map((t) => [t, titleCase(t)]))

const EMPTY = { company: "", position: "", link: "", description: "", post_id: "" }

// Side drawer to add a posting by hand. It is queued, then scored and saved by the next search run.
export function AddPositionDrawer({ disabled, onAdd }: { disabled: boolean; onAdd: (p: ManualPosition) => void }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [jobType, setJobType] = useState<JobType>("unknown")

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))
  const valid = form.company.trim() && form.position.trim() && /^https?:\/\//.test(form.link.trim()) && form.description.trim()

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!valid) return
    onAdd({
      company: form.company.trim(),
      position: form.position.trim(),
      link: form.link.trim(),
      description: form.description.trim(),
      job_type: jobType,
      post_id: form.post_id.trim() || null,
    })
    setForm(EMPTY)
    setJobType("unknown")
    setOpen(false)
  }

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)} disabled={disabled}>
        <Plus />
        Add position
      </Button>
      <Drawer open={open} onOpenChange={setOpen} swipeDirection="right">
        <DrawerContent className="sm:[--drawer-content-width:28rem]">
          <form onSubmit={submit} className="flex h-full flex-col">
            <DrawerHeader>
              <DrawerTitle>Add a position</DrawerTitle>
              <DrawerDescription>It is scored against your profile and saved on the next search run.</DrawerDescription>
            </DrawerHeader>

            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <Field label="Company" id="mp-company">
                <Input id="mp-company" value={form.company} onChange={set("company")} required />
              </Field>
              <Field label="Position" id="mp-position">
                <Input id="mp-position" value={form.position} onChange={set("position")} required />
              </Field>
              <Field label="Link" id="mp-link">
                <Input id="mp-link" type="url" value={form.link} onChange={set("link")} placeholder="https://" required />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Job type" id="mp-type">
                  <Select items={JOB_TYPE_ITEMS} value={jobType} onValueChange={(v) => v && setJobType(v as JobType)}>
                    <SelectTrigger id="mp-type" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {JOB_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {titleCase(t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Post id (optional)" id="mp-post">
                  <Input id="mp-post" value={form.post_id} onChange={set("post_id")} />
                </Field>
              </div>
              <Field label="Description" id="mp-description">
                <Textarea
                  id="mp-description"
                  value={form.description}
                  onChange={set("description")}
                  placeholder="Paste the job description; the qualification agent needs it to score the posting."
                  className="min-h-48"
                  required
                />
              </Field>
            </div>

            <DrawerFooter className="flex-row justify-end border-t pt-4">
              <DrawerClose render={<Button type="button" variant="ghost" />}>Cancel</DrawerClose>
              <Button type="submit" disabled={!valid}>
                Queue position
              </Button>
            </DrawerFooter>
          </form>
        </DrawerContent>
      </Drawer>
    </>
  )
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  )
}
