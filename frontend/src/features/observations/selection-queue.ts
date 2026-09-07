export interface SelectionState {
  selectedIds?: number[];
  isPending: boolean;
  isError: boolean;
}

/** 一次只发一个写请求；等待期间的新选择合并为最新值，页面反馈不等待网络。 */
export function createSelectionQueue(
  save: (ids: number[]) => Promise<void>,
  refresh: () => Promise<void>,
  publish: (state: SelectionState) => void,
) {
  let desired: number[] = [];
  let revision = 0;
  let running: Promise<void> | undefined;
  let error: Error | undefined;

  async function drain() {
    while (true) {
      const savingRevision = revision;
      try {
        await save([...desired]);
        if (savingRevision !== revision) continue;
        await refresh();
        if (savingRevision !== revision) continue;
        publish({ isPending: false, isError: false });
        return;
      } catch (cause) {
        // 较早的请求失败时仍保存老师后续的新选择，避免丢掉最后一次操作。
        if (savingRevision !== revision) continue;
        error = cause instanceof Error ? cause : new Error("观察对象未保存");
        publish({ selectedIds: [...desired], isPending: false, isError: true });
        throw error;
      }
    }
  }

  function select(ids: number[]) {
    desired = [...ids];
    revision += 1;
    error = undefined;
    publish({ selectedIds: [...desired], isPending: true, isError: false });
    if (!running) {
      running = drain().finally(() => { running = undefined; });
      // 点击入口的失败由界面呈现；flush 仍会抛错，阻止依赖未保存数据的操作。
      void running.catch(() => {});
    }
  }

  return {
    select,
    retry: () => select(desired),
    flush: () => error ? Promise.reject(error) : running ?? Promise.resolve(),
  };
}
