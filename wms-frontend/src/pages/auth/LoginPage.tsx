import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router-dom'
import { Warehouse, Lock, Mail } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import toast from 'react-hot-toast'

const schema = z.object({
  email: z.string().email('Correo inválido'),
  password: z.string().min(6, 'Mínimo 6 caracteres'),
})
type FormData = z.infer<typeof schema>

export function LoginPage() {
  const navigate = useNavigate()
  const { login, isLoading } = useAuthStore()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) })

  const onSubmit = async (data: FormData) => {
    try {
      await login(data.email, data.password)
      toast.success('Bienvenido al WMS Panama')
      navigate('/')
    } catch {
      toast.error('Credenciales incorrectas. Verifica tu usuario y contraseña.')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-sidebar via-primary-950 to-primary-900 flex items-center justify-center p-4">
      <div className="w-full max-w-sm animate-slide-in">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary-600 mb-4 shadow-lg">
            <Warehouse className="h-7 w-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">WMS Panama</h1>
          <p className="text-sm text-gray-400 mt-1">Warehouse Management System</p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Iniciar Sesión</h2>

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                {...register('email')}
                type="email"
                label="Correo electrónico"
                placeholder="usuario@empresa.com"
                error={errors.email?.message}
                className="pl-9"
                autoComplete="email"
              />
            </div>

            <div className="relative">
              <Lock className="absolute left-3 top-[38px] h-4 w-4 text-gray-400" />
              <Input
                {...register('password')}
                type="password"
                label="Contraseña"
                placeholder="••••••••"
                error={errors.password?.message}
                className="pl-9"
                autoComplete="current-password"
              />
            </div>

            <Button
              type="submit"
              loading={isLoading}
              className="w-full mt-2"
              size="lg"
            >
              Entrar al sistema
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-gray-400">
            WMS Panama v1.0 — Powered by FastAPI + React
          </p>
        </div>
      </div>
    </div>
  )
}
