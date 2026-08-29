import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

export type QueryTab = 'voice' | 'text'

export function QueryForm({
  activeTab,
  onTabChange,
  onStartRecording,
  textInput,
  onTextInputChange,
  onTextSubmit,
}: {
  activeTab: QueryTab
  onTabChange: (tab: QueryTab) => void
  onStartRecording: () => void
  textInput: string
  onTextInputChange: (value: string) => void
  onTextSubmit: (event: React.FormEvent) => void
}) {
  return (
    <Tabs value={activeTab} onValueChange={(value) => onTabChange(value as QueryTab)}>
      <TabsList className="mx-auto">
        <TabsTrigger value="voice">Voice</TabsTrigger>
        <TabsTrigger value="text">Text</TabsTrigger>
      </TabsList>

      <TabsContent value="voice" className="flex flex-col items-center gap-4 pt-4">
        <Button size="lg" onClick={onStartRecording}>
          Ask a question
        </Button>
      </TabsContent>

      <TabsContent value="text" className="pt-4">
        <form className="flex flex-col gap-3" onSubmit={onTextSubmit}>
          <Textarea
            placeholder="When's the next train from Richmond to Flinders Street?"
            className="min-h-28 resize-none text-base"
            value={textInput}
            onChange={(event) => onTextInputChange(event.target.value)}
          />
          <Button type="submit" size="lg" disabled={!textInput.trim()}>
            Ask
          </Button>
        </form>
      </TabsContent>
    </Tabs>
  )
}
