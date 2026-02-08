import Shell from '@/components/Shell'
import Hero from '@/components/Hero'
import Starfield from '@/visuals/Starfield'

export default function Page() {
  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <Hero />
        </Shell>
      </div>
    </>
  )
}
