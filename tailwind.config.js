/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#7C3AED',
          dark: '#5B21B6',
          soft: '#F3EDFF',
        },
        background: '#F8F7FC',
        surface: '#FFFFFF',
        text: {
          DEFAULT: '#1F2430',
          secondary: '#687280',
        },
        success: '#22C55E',
        warning: '#F59E0B',
        danger: '#EF4444',
        info: '#3B82F6',
      },
      borderRadius: {
        card: '8px',
        button: '8px',
      },
      maxWidth: {
        'mobile': '390px',
        'tablet': '768px',
      },
      minHeight: {
        'touch': '44px',
      },
    },
  },
  plugins: [],
}
