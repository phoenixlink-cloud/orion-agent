import Shell from '@/components/Shell'
import ChatInterface from '@/components/ChatInterface'
import Starfield from '@/visuals/Starfield'

export default function ChatPage() {
  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <ChatInterface />
        </Shell>
      </div>
    </>
  )
}
