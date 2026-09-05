import { ArrowLeft } from "lucide-react";
import { useNavigate } from "react-router";

/**
 * 返回上一屏的箭头按钮。
 *
 * 用浏览器历史回退（navigate(-1)）而不是写死某个路由，
 * 这样"从哪个页面进来，按返回就回到哪个页面"，而不是一律跳回首页。
 *
 * 注意：直接打开无历史记录的页面时回退可能无效（移动端通常没问题），
 * 需要"回到固定页"的场合请另用 <Link to="...">。
 */
export function BackButton({
  className,
  label = "返回",
  size = 22,
}: {
  className?: string;
  label?: string;
  size?: number;
}) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      aria-label={label}
      className={className}
      onClick={() => navigate(-1)}
    >
      <ArrowLeft size={size} />
    </button>
  );
}
