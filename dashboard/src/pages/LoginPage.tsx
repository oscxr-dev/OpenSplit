import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import axios from 'axios';
import { LockKeyhole } from 'lucide-react';
import { toast } from 'sonner';
import { BrandMark } from '@/components/brand/BrandMark';
import { loginSchema, type LoginFormData } from '@/schemas/auth';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { useAuth } from '@/hooks/useAuth';
import { isAuthenticated } from '@/lib/auth';

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  useEffect(() => {
    if (isAuthenticated()) {
      navigate('/', { replace: true });
    }
  }, [navigate]);

  async function onSubmit(data: LoginFormData) {
    try {
      await login(data.email, data.password);
      navigate('/', { replace: true });
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        toast.error('Invalid credentials. Check your email and password.');
        return;
      }

      toast.error('Could not connect to OpenSplit. Check that the API is running.');
    }
  }

  return (
    <div className="umbrel-app relative flex min-h-screen items-center justify-center overflow-hidden p-4">
      <div className="umbrel-wallpaper" aria-hidden="true" />
      <div className="umbrel-wallpaper-shade" aria-hidden="true" />
      <div className="relative z-10 w-full max-w-sm">
        <div className="rounded-[28px] border border-white/10 bg-[#17141f]/70 p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.09),0_35px_100px_rgba(0,0,0,0.48)] backdrop-blur-3xl sm:p-8">
          <div className="mb-8 flex flex-col items-center gap-3">
            <BrandMark size="lg" className="bg-[#FF2D78]/12 shadow-[inset_0_1px_0_rgba(255,255,255,0.18),0_16px_34px_rgba(255,45,120,0.18)]" />
            <h1 className="text-2xl font-semibold tracking-tight text-white/90">OpenSplit</h1>
            <p className="text-sm text-white/40">Your node, your payments, your rules.</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            <Input
              label="Email"
              type="email"
              placeholder="admin@bitcrew.example"
              autoComplete="email"
              error={errors.email?.message}
              {...register('email')}
            />

            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              autoComplete="current-password"
              error={errors.password?.message}
              {...register('password')}
            />

            <Button
              type="submit"
              loading={isSubmitting}
              className="w-full"
              size="lg"
            >
              <LockKeyhole className="h-4 w-4" />
              Unlock
            </Button>
          </form>
        </div>
        <p className="mt-5 text-center text-[11px] tracking-wide text-white/25">
          Protected local connection
        </p>
      </div>
    </div>
  );
}
