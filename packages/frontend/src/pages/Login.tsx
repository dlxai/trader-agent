import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Eye, EyeOff, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useAuth } from '@/hooks/useAuth'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register, isLoading, error, clearError } = useAuth()

  const [isRegisterMode, setIsRegisterMode] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    confirmPassword: '',
  })
  const [formErrors, setFormErrors] = useState<Record<string, string>>({})

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard'

  const validateForm = () => {
    const errors: Record<string, string> = {}

    if (isRegisterMode) {
      if (!formData.email) {
        errors.email = '请输入邮箱'
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
        errors.email = '请输入有效的邮箱地址'
      }
    }

    // Login mode: allow email (contains @) or username
    // Register mode: strict username validation
    if (isRegisterMode) {
      if (!formData.username) {
        errors.username = '请输入用户名'
      } else if (formData.username.length < 3) {
        errors.username = '用户名至少3个字符'
      } else if (!/^[a-zA-Z0-9_]+$/.test(formData.username)) {
        errors.username = '用户名只能包含字母、数字和下划线'
      }
    } else {
      // Login mode: just require non-empty
      if (!formData.username) {
        errors.username = '请输入用户名'
      }
    }

    if (!formData.password) {
      errors.password = '请输入密码'
    } else if (formData.password.length < 8) {
      errors.password = '密码至少8个字符'
    }

    if (isRegisterMode) {
      if (!formData.confirmPassword) {
        errors.confirmPassword = '请确认密码'
      } else if (formData.confirmPassword !== formData.password) {
        errors.confirmPassword = '两次密码不一致'
      }
    }

    setFormErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()

    if (!validateForm()) return

    try {
      if (isRegisterMode) {
        await register({
          email: formData.email,
          username: formData.username,
          password: formData.password,
        })
      } else {
        await login({ username: formData.username, password: formData.password })
      }
      navigate(from, { replace: true })
    } catch {
      // Error is handled by store
    }
  }

  const toggleMode = () => {
    setIsRegisterMode(!isRegisterMode)
    setFormErrors({})
    clearError()
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background p-4">
      <div className="w-full max-w-md space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500 shadow-lg shadow-emerald-500/20">
            <Wallet className="h-8 w-8 text-black" />
          </div>
          <h1 className="mt-6 text-3xl font-bold tracking-tight">
            WestGardeng 量化交易
          </h1>
          <p className="mt-2 text-muted-foreground">
            专业预测市场交易平台
          </p>
        </div>

        {/* Login Form */}
        <div className="rounded-2xl border border-border bg-muted/50 p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500">
                {error}
              </div>
            )}

            {isRegisterMode && (
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="email">
                  邮箱
                </label>
                <Input
                  id="email"
                  type="email"
                  placeholder="请输入邮箱"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData((prev) => ({ ...prev, email: e.target.value }))
                  }
                  error={formErrors.email}
                  disabled={isLoading}
                />
              </div>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="username">
                用户名
              </label>
              <Input
                id="username"
                type="text"
                placeholder="请输入用户名"
                value={formData.username}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, username: e.target.value }))
                }
                error={formErrors.username}
                disabled={isLoading}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="password">
                密码
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="请输入密码"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData((prev) => ({
                      ...prev,
                      password: e.target.value,
                    }))
                  }
                  error={formErrors.password}
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {isRegisterMode && (
              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="confirmPassword">
                  确认密码
                </label>
                <div className="relative">
                  <Input
                    id="confirmPassword"
                    type={showConfirmPassword ? 'text' : 'password'}
                    placeholder="请再次输入密码"
                    value={formData.confirmPassword}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        confirmPassword: e.target.value,
                      }))
                    }
                    error={formErrors.confirmPassword}
                    disabled={isLoading}
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              size="lg"
              isLoading={isLoading}
            >
              {isRegisterMode ? '注册账号' : '登录'}
            </Button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-sm text-muted-foreground">
          {isRegisterMode ? (
            <>
              已有账号？{' '}
              <button
                onClick={toggleMode}
                className="text-emerald-500 hover:text-emerald-400 font-medium"
              >
                立即登录
              </button>
            </>
          ) : (
            <>
              首次使用？{' '}
              <button
                onClick={toggleMode}
                className="text-emerald-500 hover:text-emerald-400 font-medium"
              >
                创建账号
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}