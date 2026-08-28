import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { requestJson } from "../../api/http";
import { FEATURES } from "../../config/features";

export interface Classroom {
  id: number;
  name: string;
  /** 该班在册幼儿数，后端聚合返回，前端不自己算 */
  child_count: number;
}

export interface KindergartenTeacher {
  id: number;
  name: string;
  phone: string | null;
  classroom_id: number | null;
  /** owner = 建园的人，可以改园所名和增删班级 */
  role: "owner" | "teacher";
}

export interface Kindergarten {
  id: number;
  name: string;
  classrooms: Classroom[];
  teachers: KindergartenTeacher[];
  /** 当前登录教师在这个园里的角色 */
  my_role: "owner" | "teacher";
}

const keys = { current: ["kindergarten", "current"] as const };

export function useKindergarten() {
  return useQuery({
    queryKey: keys.current,
    queryFn: () =>
      requestJson<Kindergarten>("/kindergartens/current", {
        method: "GET",
        fallbackMessage: "园所信息加载失败",
      }),
    enabled: FEATURES.kindergarten,
  });
}

function useKindergartenMutation<TArgs>(
  run: (args: TArgs) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.current });
    },
  });
}

export function useRenameKindergarten() {
  return useKindergartenMutation<string>((name) =>
    requestJson<Kindergarten>("/kindergartens/current", {
      method: "PATCH",
      body: JSON.stringify({ name: name.trim() }),
      fallbackMessage: "园所名称没有保存成功",
    }),
  );
}

export function useCreateClassroom() {
  return useKindergartenMutation<string>((name) =>
    requestJson<Classroom>("/classrooms", {
      method: "POST",
      body: JSON.stringify({ name: name.trim() }),
      fallbackMessage: "班级没有添加成功",
    }),
  );
}

export function useRenameClassroom() {
  return useKindergartenMutation<{ id: number; name: string }>(({ id, name }) =>
    requestJson<Classroom>(`/classrooms/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name: name.trim() }),
      fallbackMessage: "班级名称没有保存成功",
    }),
  );
}

/**
 * 删除班级。
 * 后端约定：班里还有幼儿时返回 409，body.detail 说明还剩几名，前端直接展示这句话。
 * 不做「连同幼儿一起删」的选项——那是误删数据的常见来源。
 */
export function useDeleteClassroom() {
  return useKindergartenMutation<number>((id) =>
    requestJson<void>(`/classrooms/${id}`, {
      method: "DELETE",
      fallbackMessage: "班级没有删除成功",
    }),
  );
}
