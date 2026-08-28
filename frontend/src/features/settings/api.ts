import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";

export type Child = components["schemas"]["ChildResponse"];
export type ChildUpdate = components["schemas"]["ChildUpdate"];
export type Teacher = components["schemas"]["TeacherResponse"];
export type TeacherUpdate = components["schemas"]["TeacherUpdate"];

const settingsKeys = {
  children: ["settings", "children"] as const,
  teachers: ["settings", "teachers"] as const,
};

async function getChildren() {
  const { data, error } = await apiClient.GET("/children");
  if (error || !data) throw new Error("幼儿信息加载失败");
  return data;
}

async function getTeachers() {
  const { data, error } = await apiClient.GET("/teachers");
  if (error || !data) throw new Error("教师信息加载失败");
  return data;
}

export function useSettingsData() {
  const children = useQuery({ queryKey: settingsKeys.children, queryFn: getChildren });
  const teachers = useQuery({ queryKey: settingsKeys.teachers, queryFn: getTeachers });
  return { children, teachers };
}

export function useUpdateChild() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: ChildUpdate }) => {
      const { data, error } = await apiClient.PATCH("/children/{child_id}", {
        params: { path: { child_id: id } },
        body,
      });
      if (error || !data) throw new Error("幼儿信息保存失败");
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.children });
    },
  });
}

export function useUpdateTeacher() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, body }: { id: number; body: TeacherUpdate }) => {
      const { data, error } = await apiClient.PATCH("/teachers/{teacher_id}", {
        params: { path: { teacher_id: id } },
        body,
      });
      if (error || !data) throw new Error("教师信息保存失败");
      return data;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: settingsKeys.teachers });
    },
  });
}
