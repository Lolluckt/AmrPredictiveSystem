
import { useEffect } from "react";
import { useLiveChannel, type LiveStatus } from "@/api/ws";

export const liveStatusEvent = "amr:live-status";

declare global {
  interface WindowEventMap {
    "amr:live-status": CustomEvent<LiveStatus>;
  }
}

export function LiveChannelHost() {
  const { status } = useLiveChannel();
  useEffect(() => {
    window.dispatchEvent(new CustomEvent(liveStatusEvent, { detail: status }));
  }, [status]);
  return null;
}
