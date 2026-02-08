import Shell from '@/components/Shell'
import AegisInfo from '@/components/AegisInfo'
import Starfield from '@/visuals/Starfield'

export default function AegisPage() {
  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <AegisInfo />
        </Shell>
      </div>
    </>
  )
}
