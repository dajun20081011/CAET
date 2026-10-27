import lottie from 'lottie-web';
import {
  onBeforeUnmount,
  onMounted,
  shallowRef,
  watch,
  type Ref,
  type WatchStopHandle,
} from 'vue';
import { useReducedMotion } from './useReducedMotion';

type LottieSource =
  | { path: string; animationData?: never }
  | { animationData: object; path?: never };

type LottieOptions = {
  autoplay?: boolean;
  loop?: boolean;
  renderer?: 'svg' | 'canvas' | 'html';
};

type LottieInstance = ReturnType<typeof lottie.loadAnimation>;

export function useLottie(
  container: Ref<HTMLElement | null>,
  source: LottieSource,
  options: LottieOptions = {},
) {
  const reducedMotion = useReducedMotion();
  const animation = shallowRef<LottieInstance | null>(null);
  let stopWatching: WatchStopHandle | undefined;

  onMounted(() => {
    const element = container.value;
    if (!element) return;

    const shouldAutoplay = options.autoplay ?? true;
    const common = {
      container: element,
      renderer: options.renderer ?? 'svg',
      loop: options.loop ?? false,
      autoplay: shouldAutoplay && !reducedMotion.value,
    } as const;

    animation.value = 'path' in source
      ? lottie.loadAnimation({ ...common, path: source.path })
      : lottie.loadAnimation({ ...common, animationData: source.animationData });

    stopWatching = watch(reducedMotion, (reduced) => {
      if (!animation.value) return;
      if (reduced) animation.value.pause();
      else if (shouldAutoplay) animation.value.play();
    });
  });

  onBeforeUnmount(() => {
    stopWatching?.();
    animation.value?.destroy();
    animation.value = null;
  });

  return { animation };
}
