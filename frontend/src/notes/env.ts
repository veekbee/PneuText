// How note bodies reach the rest of the app: page addresses, figure images, navigation.
import { figureFileUrl } from "../api/client";
import { pagePath } from "../lib/route";
import { navigate } from "../router";
import type { NoteEnv } from "./NoteBody";

export const APP_ENV: NoteEnv = {
  pageHref: pagePath,
  figureSrc: figureFileUrl,
  navigate,
};
