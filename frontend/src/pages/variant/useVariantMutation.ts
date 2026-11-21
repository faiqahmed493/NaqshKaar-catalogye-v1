import { useMutation, useQueryClient } from "@tanstack/react-query";

/** Run an API call, then refresh this variant (and lists that show it). */
export function useVariantMutation<TArgs, TResult = unknown>(variantId: string, fn: (args: TArgs) => Promise<TResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["variant", variantId] });
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
  });
}
