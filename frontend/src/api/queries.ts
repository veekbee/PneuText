import { useQuery } from "@tanstack/react-query";

import { api } from "./client";

export function useLibrary() {
  return useQuery({ queryKey: ["library"], queryFn: api.getLibrary });
}
