import { Toaster as Sonner, type ToasterProps } from "sonner"
import { CheckCircle, Info, Warning, XCircle, SpinnerGap } from "@phosphor-icons/react"

const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      duration={2000}
      icons={{
        success: (
          <CheckCircle size={16} />
        ),
        info: (
          <Info size={16} />
        ),
        warning: (
          <Warning size={16} />
        ),
        error: (
          <XCircle size={16} />
        ),
        loading: (
          <SpinnerGap size={16} className="animate-spin" />
        ),
      }}
      style={
        {
          "--normal-bg": "var(--color-popover)",
          "--normal-text": "var(--color-popover-foreground)",
          "--normal-border": "var(--color-border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
