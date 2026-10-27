import { onBeforeUnmount, onMounted, ref } from 'vue';

export function useReducedMotion() {
  const prefersReducedMotion = ref(false);
  let media: MediaQueryList | undefined;

  const update = (event: MediaQueryListEvent) => {
    prefersReducedMotion.value = event.matches;
  };

  onMounted(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    media = window.matchMedia('(prefers-reduced-motion: reduce)');
    prefersReducedMotion.value = media.matches;
    media.addEventListener('change', update);
  });

  onBeforeUnmount(() => {
    media?.removeEventListener('change', update);
  });

  return prefersReducedMotion;
}
