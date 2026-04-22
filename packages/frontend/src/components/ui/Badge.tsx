import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-emerald-500 text-black hover:bg-emerald-600',
        secondary:
          'border-transparent bg-muted text-foreground hover:bg-muted/80',
        destructive:
          'border-transparent bg-red-500 text-white hover:bg-red-600',
        outline:
          'border-border text-foreground hover:bg-muted',
        success:
          'border-transparent bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20',
        warning:
          'border-transparent bg-yellow-500/10 text-yellow-500 hover:bg-yellow-500/20',
        error:
          'border-transparent bg-red-500/10 text-red-500 hover:bg-red-500/20',
        info:
          'border-transparent bg-blue-500/10 text-blue-500 hover:bg-blue-500/20',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
  dotColor?: string
}

function Badge({
  className,
  variant,
  dot,
  dotColor,
  children,
  ...props
}: BadgeProps) {
  return (
    <div
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    >
      {dot && (
        <span
          className="mr-1.5 h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: dotColor || 'currentColor' }}
        />
      )}
      {children}
    </div>
  )
}

export { Badge, badgeVariants }
