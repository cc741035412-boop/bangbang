import { createSelectionQueue, type SelectionState } from "./selection-queue";

function deferred() {
  let resolve: () => void = () => {};
  let reject: (error: Error) => void = () => {};
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

it("慢请求未返回也立即反馈，连续切换只保存首个和最后一个状态", async () => {
  const first = deferred(), last = deferred();
  const save = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(last.promise);
  const states: SelectionState[] = [];
  const refresh = vi.fn().mockResolvedValue(undefined);
  const queue = createSelectionQueue(save, refresh, (state) => states.push(state));
  queue.select([1, 2]);
  queue.select([2, 1]);
  queue.select([3, 2, 1]);
  expect(states.at(-1)).toEqual({ selectedIds: [3, 2, 1], isPending: true, isError: false });
  expect(save).toHaveBeenCalledTimes(1);
  first.resolve();
  await vi.waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  expect(save).toHaveBeenLastCalledWith([3, 2, 1]);
  expect(refresh).not.toHaveBeenCalled();
  let finished = false;
  const flushed = queue.flush().then(() => { finished = true; });
  expect(finished).toBe(false);
  last.resolve();
  await flushed;
  expect(refresh).toHaveBeenCalledOnce();
  expect(states.at(-1)).toEqual({ isPending: false, isError: false });
});

it("失败保留最新角色选择，阻止下一步并可重试", async () => {
  const failed = deferred();
  const save = vi.fn().mockReturnValueOnce(failed.promise).mockResolvedValueOnce(undefined);
  const publish = vi.fn();
  const queue = createSelectionQueue(save, async () => {}, publish);
  queue.select([2, 1]);
  failed.reject(new Error("offline"));
  await expect(queue.flush()).rejects.toThrow("offline");
  expect(publish).toHaveBeenLastCalledWith({ selectedIds: [2, 1], isPending: false, isError: true });
  await expect(queue.flush()).rejects.toThrow("offline");
  queue.retry();
  await queue.flush();
  expect(save).toHaveBeenLastCalledWith([2, 1]);
  expect(publish).toHaveBeenLastCalledWith({ isPending: false, isError: false });
});

it("读回期间继续切换，旧读取完成也不能清除新选择", async () => {
  const reading = deferred();
  const save = vi.fn().mockResolvedValue(undefined);
  const refresh = vi.fn().mockReturnValueOnce(reading.promise).mockResolvedValue(undefined);
  const publish = vi.fn();
  const queue = createSelectionQueue(save, refresh, publish);
  queue.select([1]);
  await vi.waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  queue.select([2, 1]);
  expect(publish).toHaveBeenLastCalledWith({ selectedIds: [2, 1], isPending: true, isError: false });
  reading.resolve();
  await queue.flush();
  expect(save.mock.calls).toEqual([[[1]], [[2, 1]]]);
  expect(refresh).toHaveBeenCalledTimes(2);
});
