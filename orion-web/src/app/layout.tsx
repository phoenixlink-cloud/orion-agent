import type { Metadata } from 'next'
import '@/design/tokens.css'
import AegisApprovalProvider from '@/components/AegisApprovalProvider'

export const metadata: Metadata = {
  title: 'Orion - Governed AI Assistant',
  description: 'I\'m here to help you create — safely.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        {children}
        <AegisApprovalProvider />
      </body>
    </html>
  )
}
