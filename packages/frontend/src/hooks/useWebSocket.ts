import { useEffect, useRef, useCallback, useState } from 'react'
import { io, type Socket } from 'socket.io-client'
import type {
  WebSocketMessage,
  PriceUpdateMessage,
  OrderUpdateMessage,
  PositionUpdateMessage,
  TradeMessage,
  SystemMessage,
} from '@/types'

const WS_URL = import.meta.env.VITE_WS_URL || window.location.origin

interface UseWebSocketOptions {
  autoConnect?: boolean
  onConnect?: () => void
  onDisconnect?: (reason: string) => void
  onError?: (error: Error) => void
  onPriceUpdate?: (data: PriceUpdateMessage['data']) => void
  onOrderUpdate?: (data: OrderUpdateMessage['data']) => void
  onPositionUpdate?: (data: PositionUpdateMessage['data']) => void
  onTrade?: (data: TradeMessage['data']) => void
  onSystemMessage?: (data: SystemMessage['data']) => void
}

interface UseWebSocketReturn {
  socket: Socket | null
  isConnected: boolean
  connect: () => void
  disconnect: () => void
  subscribe: (channel: string, data?: Record<string, unknown>) => void
  unsubscribe: (channel: string, data?: Record<string, unknown>) => void
  emit: (event: string, data: unknown) => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    autoConnect = true,
    onConnect,
    onDisconnect,
    onError,
    onPriceUpdate,
    onOrderUpdate,
    onPositionUpdate,
    onTrade,
    onSystemMessage,
  } = options

  const socketRef = useRef<Socket | null>(null)
  const [isConnected, setIsConnected] = useState(false)

  // Message handler
  const handleMessage = useCallback(
    (message: WebSocketMessage) => {
      switch (message.type) {
        case 'price':
          onPriceUpdate?.(message.data)
          break
        case 'order':
          onOrderUpdate?.(message.data)
          break
        case 'position':
          onPositionUpdate?.(message.data)
          break
        case 'trade':
          onTrade?.(message.data)
          break
        case 'system':
          onSystemMessage?.(message.data)
          break
      }
    },
    [onPriceUpdate, onOrderUpdate, onPositionUpdate, onTrade, onSystemMessage]
  )

  // Connect function
  const connect = useCallback(() => {
    if (socketRef.current?.connected) return

    const token = localStorage.getItem('accessToken')

    const socket = io(WS_URL, {
      transports: ['websocket'],
      auth: token ? { token } : undefined,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
    })

    socket.on('connect', () => {
      setIsConnected(true)
      onConnect?.()
    })

    socket.on('disconnect', (reason) => {
      setIsConnected(false)
      onDisconnect?.(reason)
    })

    socket.on('error', (error: Error) => {
      onError?.(error)
    })

    // Listen for typed messages
    socket.on('price', (data: PriceUpdateMessage['data']) => {
      handleMessage({ type: 'price', data })
    })

    socket.on('order', (data: OrderUpdateMessage['data']) => {
      handleMessage({ type: 'order', data })
    })

    socket.on('position', (data: PositionUpdateMessage['data']) => {
      handleMessage({ type: 'position', data })
    })

    socket.on('trade', (data: TradeMessage['data']) => {
      handleMessage({ type: 'trade', data })
    })

    socket.on('system', (data: SystemMessage['data']) => {
      handleMessage({ type: 'system', data })
    })

    socketRef.current = socket
  }, [handleMessage, onConnect, onDisconnect, onError])

  // Disconnect function
  const disconnect = useCallback(() => {
    socketRef.current?.disconnect()
    socketRef.current = null
    setIsConnected(false)
  }, [])

  // Subscribe to channel
  const subscribe = useCallback((channel: string, data?: Record<string, unknown>) => {
    socketRef.current?.emit('subscribe', { channel, ...data })
  }, [])

  // Unsubscribe from channel
  const unsubscribe = useCallback((channel: string, data?: Record<string, unknown>) => {
    socketRef.current?.emit('unsubscribe', { channel, ...data })
  }, [])

  // Emit custom event
  const emit = useCallback((event: string, data: unknown) => {
    socketRef.current?.emit(event, data)
  }, [])

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect()
    }

    return () => {
      disconnect()
    }
  }, [autoConnect, connect, disconnect])

  return {
    socket: socketRef.current,
    isConnected,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    emit,
  }
}
