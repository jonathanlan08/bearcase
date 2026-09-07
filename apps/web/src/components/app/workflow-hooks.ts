"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type Progress, type SellerQuestions, type Usage } from "@/lib/api";

/**
 * Queries for the buyer workflow (documents → findings → evidence → questions for the seller) and the usage panel.
 * Same shape as `components/app/hooks.ts`: every key carries the deal id, so `useInvalidateDeal` and the process
 * mutation's predicate refresh these rows along with the rest of the deal.
 */
export const wqk = {
  progress: (id: string) => ["progress", id] as const,
  sellerQuestions: (id: string) => ["sellerQuestions", id] as const,
  usage: (id: string) => ["usage", id] as const,
};

/** Which of the four workflow steps the user has completed; the API decides from persisted rows, never from page views. */
export const useProgress = (id: string) => useQuery({ queryKey: wqk.progress(id), queryFn: () => api.get<Progress>(`/api/deals/${id}/progress`) });
export const useSellerQuestions = (id: string) => useQuery({ queryKey: wqk.sellerQuestions(id), queryFn: () => api.get<SellerQuestions>(`/api/deals/${id}/seller-questions`) });
export const useUsage = (id: string) => useQuery({ queryKey: wqk.usage(id), queryFn: () => api.get<Usage>(`/api/deals/${id}/usage`) });
