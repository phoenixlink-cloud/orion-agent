import Shell from '@/components/Shell'
import SettingsPanel from '@/components/SettingsPanel'
import Starfield from '@/visuals/Starfield'

export default function SettingsPage() {
  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <SettingsPanel />
        </Shell>
      </div>
    </>
  )
}
