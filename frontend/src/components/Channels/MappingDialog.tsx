import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check } from "lucide-react"
import { useState } from "react"

import {
  FacebookPagesService,
  MappingsService,
  type TikTokChannelRead,
} from "@/client"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface MappingDialogProps {
  channel: TikTokChannelRead
  isOpen: boolean
  onOpenChange: (open: boolean) => void
}

const MappingDialog = ({
  channel,
  isOpen,
  onOpenChange,
}: MappingDialogProps) => {
  const [selected, setSelected] = useState<number[]>([])
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const mappedIds = new Set(
    (channel.pages ?? []).map((p) => Number((p as { id?: number }).id)),
  )

  const { data: pages, isLoading } = useQuery({
    queryKey: ["pages"],
    queryFn: () => FacebookPagesService.listPages(),
    enabled: isOpen,
  })

  const mutation = useMutation({
    mutationFn: async (pageIds: number[]) => {
      for (const id of pageIds) {
        await MappingsService.createMapping({
          requestBody: { tiktok_channel_id: channel.id, facebook_page_id: id },
        })
      }
    },
    onSuccess: () => {
      showSuccessToast("Mappings saved")
      setSelected([])
      onOpenChange(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["channels"] })
      queryClient.invalidateQueries({ queryKey: ["pages"] })
    },
  })

  const toggle = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const submit = () => {
    mutation.mutate(selected)
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Manage Pages for @{channel.username}</DialogTitle>
          <DialogDescription>
            Select Facebook pages that should receive this channel's videos.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 py-4">
          {isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            (pages ?? []).map((page) => {
              const isMapped = mappedIds.has(page.id)
              const isSelected = selected.includes(page.id)
              return (
                <Label
                  key={page.id}
                  className="flex items-center gap-3 border rounded-lg px-3 py-2 cursor-pointer"
                >
                  <Checkbox
                    checked={isMapped || isSelected}
                    disabled={isMapped}
                    onCheckedChange={() => toggle(page.id)}
                  />
                  <span className="flex-1">
                    <span className="font-medium block">{page.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {page.page_id}
                    </span>
                  </span>
                  {isMapped && (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Check className="size-3" />
                      Mapped
                    </span>
                  )}
                </Label>
              )
            })
          )}
          {(pages ?? []).length === 0 && !isLoading && (
            <p className="text-sm text-muted-foreground">
              No Facebook pages yet. Create one on the Pages page first.
            </p>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <LoadingButton
            onClick={submit}
            loading={mutation.isPending}
            disabled={selected.length === 0}
          >
            Save Mappings
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default MappingDialog
