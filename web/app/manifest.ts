import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Server Vibe",
    short_name: "ServerVibe",
    description: "Mobile command center for remote terminal control",
    start_url: "/",
    display: "standalone",
    background_color: "#f6fbff",
    theme_color: "#8ed9ff",
    orientation: "portrait",
    icons: [
      {
        src: "/icons/icon-192.svg",
        sizes: "192x192",
        type: "image/svg+xml",
      },
      {
        src: "/icons/icon-512.svg",
        sizes: "512x512",
        type: "image/svg+xml",
      },
    ],
  };
}

