import { Rive } from '@rive-app/canvas';
import {
  onBeforeUnmount,
  onMounted,
  watch,
  type Ref,
  type WatchStopHandle,
} from 'vue';
import { useReducedMotion } from './useReducedMotion';

type RiveOptions = {
  autoplay?: boolean;
};

export function useRive(
  canvas: Ref<HTMLCanvasElement | null>,
  src: string,
  options: RiveOptions = {},
) {
  const reducedMotion = useReducedMotion();
  let instance: Rive | null = null;
  let stopWatching: WatchStopHandle | undefined;
  const shouldAutoplay = options.autoplay ?? true;

  onMounted(() => {
    const element = canvas.value;
    if (!element) return;

    instance = new Rive({
      src,
      canvas: element,
      autoplay: shouldAutoplay && !reducedMotion.value,
    });

    stopWatching = watch(reducedMotion, (reduced) => {
      if (!instance) return;
      if (reduced) instance.pause();
      else if (shouldAutoplay) instance.play();
    });
  });

  onBeforeUnmount(() => {
    stopWatching?.();
    instance?.cleanup();
    instance = null;
  });

  return {
    getInstance: () => instance,
  };
}
