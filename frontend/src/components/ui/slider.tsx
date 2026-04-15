import * as React from "react"
import * as SliderPrimitive from "@radix-ui/react-slider"

import { cn } from "@/lib/utils"

interface SliderProps extends React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> {
  size?: "default" | "sm"
}

const trackStyles = {
  default: "h-2 bg-secondary",
  sm: "h-1 bg-foreground/15",
}

const rangeStyles = {
  default: "bg-primary",
  sm: "bg-foreground/40",
}

const thumbStyles = {
  default: "h-5 w-5 border-2 border-primary bg-background",
  sm: "h-3.5 w-3.5 border-[1.5px] border-foreground/30 bg-foreground/60",
}

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  SliderProps
>(({ className, size = "default", ...props }, ref) => (
  <SliderPrimitive.Root
    ref={ref}
    className={cn(
      "relative flex w-full touch-none select-none items-center cursor-pointer",
      className
    )}
    {...props}
  >
    <SliderPrimitive.Track className={cn("relative w-full grow overflow-hidden rounded-full", trackStyles[size])}>
      <SliderPrimitive.Range className={cn("absolute h-full", rangeStyles[size])} />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb className={cn("block cursor-grab active:cursor-grabbing rounded-full ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50", thumbStyles[size])} />
  </SliderPrimitive.Root>
))
Slider.displayName = SliderPrimitive.Root.displayName

export { Slider }
