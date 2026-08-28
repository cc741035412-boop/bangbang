import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestJson } from "../../api/http";
import { FEATURES } from "../../config/features";

/**
 * 首期只做两个维度：身体参与、社会互动。
 * 「社会情感」的品质推断不做——那是伦理问题，不是准确率问题。
 * 档案页的覆盖统计只按这两个维度展开。
 */
export const PROFILE_DIMENSIONS = ["身体参与", "社会互动"] as const;

export interface ChildProfileRecord {
  observation_id: number;
  title: string;
  area_name: string | null;
  observed_at: string;
  dimensions: string[];
  exported: boolean;
}

export interface ChildProfile {
  id: number;
  name: string;
  classroom_id: number | null;
  classroom_name: string | null;
  birth_date: string | null;
  gender: "male" | "female" | null;
  created_at: string | null;
  /** 素材条数（含未生成记录的） */
  media_count: number;
  /** 已确认的观察记录数 */
  record_count: number;
  /** 有素材或有记录的自然天数 */
  observed_day_count: number;
  /**
   * 各维度被观察到的次数。
   * 注意：这是「被看到几次」，不是孩子在这方面的水平。
   * 后端只返回计数，不要返回任何评级、评分、百分位。
   */
  dimension_counts: Record<string, number>;
  records: ChildProfileRecord[];
}

export interface ChildCreate {
  name: string;
  classroom_id?: number | null;
  birth_date?: string | null;
  gender?: "male" | "female" | null;
}

const childKeys = {
  all: ["settings", "children"] as const,
  profile: (id: number) => ["children", id, "profile"] as const,
};

export function useChildProfile(childId: number) {
  return useQuery({
    queryKey: childKeys.profile(childId),
    queryFn: () =>
      requestJson<ChildProfile>(`/children/${childId}/profile`, {
        method: "GET",
        fallbackMessage: "这名幼儿的档案暂时打不开",
      }),
    enabled: FEATURES.childProfile && Number.isInteger(childId) && childId > 0,
  });
}

export function useCreateChild() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ChildCreate) =>
      requestJson<{ id: number; name: string }>("/children", {
        method: "POST",
        body: JSON.stringify({ ...body, name: body.name.trim() }),
        fallbackMessage: "幼儿没有添加成功",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: childKeys.all });
      await queryClient.invalidateQueries({ queryKey: ["children"] });
    },
  });
}

/**
 * 删除幼儿。
 * 后端约定：这名幼儿名下还有素材或记录时返回 409，
 * detail 里说明还剩多少条，前端原样展示，不提供「连同记录一起删」的快捷方式。
 */
export function useDeleteChild() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (childId: number) =>
      requestJson<void>(`/children/${childId}`, {
        method: "DELETE",
        fallbackMessage: "幼儿没有删除成功",
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: childKeys.all });
      await queryClient.invalidateQueries({ queryKey: ["children"] });
    },
  });
}
