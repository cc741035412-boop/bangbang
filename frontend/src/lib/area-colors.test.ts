import { Blocks, Shapes } from "lucide-react";
import { areaAccent } from "./area-colors";

describe("area colors", () => {
  it("为已定义的区域返回对应的标识（颜色 + 图标）", () => {
    expect(areaAccent("建构区")).toMatchObject({ dot: "#b9813f", chipBg: "#f8ecdb", chipText: "#8b5c22", icon: Blocks });
    expect(areaAccent("科探区").dot).toBe("#2f8f7c");
    expect(areaAccent("阅读区").icon).toBeDefined();
  });

  it("未知区域回退到中性灰 + 通用图标，不会给出误导颜色", () => {
    const fallback = areaAccent("自定义区");
    expect(fallback).toMatchObject({ dot: "#8b9994", chipBg: "#f0efeb", chipText: "#5f675f", icon: Shapes });
  });
});
