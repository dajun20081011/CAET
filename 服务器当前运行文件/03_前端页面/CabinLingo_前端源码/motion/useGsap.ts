import { gsap } from 'gsap';
import {
  onBeforeUnmount,
  onMounted,
  watch,
  type Ref,
  type WatchStopHandle,
} from 'vue';
import { useReducedMotion } from './useReducedMotion';

export function useGsap(
  scope: Ref<HTMLElement | null>,
  setup: () => void,
) {
  const reducedMotion = useReducedMotion();
  let context: ReturnType<typeof gsap.context> | undefined;
  let stopWatching: WatchStopHandle | undefined;

  const createAnimation = () => {
    context?.revert();
    context = undefined;

    if (reducedMotion.value || !scope.value) return;
    context = gsap.context(setup, scope.value);
  };

  onMounted(() => {
    createAnimation();
    stopWatching = watch(reducedMotion, createAnimation);
  });

  onBeforeUnmount(() => {
    stopWatching?.();
    context?.revert();
  });

  return { refresh: createAnimation };
}
