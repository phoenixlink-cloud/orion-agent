import Shell from '@/components/Shell'
import NetworkDashboard from '@/components/NetworkDashboard'
import Starfield from '@/visuals/Starfield'

export default function NetworkPage() {
  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <NetworkDashboard />
        </Shell>
      </div>
    </>
  )
}
