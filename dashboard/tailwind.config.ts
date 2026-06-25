import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bitcoin: {
          50: '#FFF0F8',
          100: '#FFE0F0',
          200: '#FFC1E2',
          300: '#FF8FCC',
          400: '#FF5BAE',
          500: '#FF2D78',
          600: '#E31867',
          700: '#BD0F55',
          800: '#971047',
          900: '#7A123D',
          DEFAULT: '#FF2D78',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
} satisfies Config;
