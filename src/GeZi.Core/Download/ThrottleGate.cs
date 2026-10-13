// GeZi —— 夸克网盘下载器 (Quark netdisk downloader)
// Copyright (C) 2026  Yi Yuan
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace GeZi.Core.Download
{
    /// <summary>
    /// 可动态收窄 / 回升的并发闸门。
    ///
    /// <para>
    /// 【为什么不用 SemaphoreSlim】原实现是"固定容量信号量 + 收窄时把多余的票偷走
    /// （<c>Wait(0)</c> 拿走且永不归还）"，这带来两个真实缺陷：
    /// </para>
    /// <para>
    /// ① <b>并发会永久性地掉下去</b>：偷走的票只能靠"每 30 秒静默补一张"慢慢还，
    /// 一旦限流持续（限流期间这 30 秒静默永远不成立），并发就再也回不来。
    /// 试验台实测：64 路在 0.35 秒内被压到下限 4 路，之后整段下载都只有 4 路，
    /// 同一个文件从 2.8 秒变成 10.3 秒 —— 也就是用户抱怨的"越下越慢 / 卡住"。
    /// </para>
    /// <para>
    /// ② <b>状态会漂移</b>：放行能力被拆成"信号量计数"和 <c>gateLimit</c> 两份状态，
    /// 回升时 <c>Release</c> 的数量与当初偷走的数量并不相等，于是日志说
    /// "并发回升到 N 路"、实际放行的却不是 N 路，无法自洽。
    /// </para>
    /// <para>
    /// 这里改成单一状态：<b><see cref="Limit"/> 就是唯一真相</b>。收窄与回升都是
    /// "改一个数 + 唤醒等待者"，没有票的搬运，因此不会漂移、也不会不可逆。
    /// </para>
    /// </summary>
    internal sealed class ThrottleGate
    {
        private readonly object _lock = new object();
        private readonly LinkedList<TaskCompletionSource<bool>> _waiters =
            new LinkedList<TaskCompletionSource<bool>>();
        private int _limit;
        private int _inFlight;

        public ThrottleGate(int limit)
        {
            _limit = limit < 1 ? 1 : limit;
        }

        /// <summary>当前并发上限（唯一起作用的状态）。</summary>
        public int Limit
        {
            get { lock (_lock) return _limit; }
        }

        /// <summary>当前在飞数（诊断用）。</summary>
        public int InFlight
        {
            get { lock (_lock) return _inFlight; }
        }

        /// <summary>
        /// 设置并发上限（下限 1）。**收窄与回升走同一条路径** ——
        /// 这正是原实现缺的那一半：能缩不能放。
        /// </summary>
        public void SetLimit(int n)
        {
            if (n < 1) n = 1;
            List<TaskCompletionSource<bool>> wake = null;
            lock (_lock)
            {
                _limit = n;
                while (_waiters.Count > 0 && _inFlight < _limit)
                {
                    _inFlight++;
                    var t = _waiters.First.Value;
                    _waiters.RemoveFirst();
                    if (wake == null) wake = new List<TaskCompletionSource<bool>>();
                    wake.Add(t);
                }
            }
            // 唤醒必须在锁外做：TrySetResult 会同步执行等待者的续体，
            // 若在锁内调用，续体里再碰这个闸门就会形成重入等待。
            if (wake != null)
            {
                for (int i = 0; i < wake.Count; i++)
                    wake[i].TrySetResult(true);
            }
        }

        /// <summary>取一张通行证（超过上限则排队等待）。取消时从队列摘除，不会占坑。</summary>
        public async Task WaitAsync(CancellationToken ct)
        {
            TaskCompletionSource<bool> tcs = null;
            CancellationTokenRegistration reg = default(CancellationTokenRegistration);

            lock (_lock)
            {
                if (_inFlight < _limit)
                {
                    _inFlight++;
                    return;
                }

                tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
                var node = _waiters.AddLast(tcs);

                if (ct.CanBeCanceled)
                {
                    reg = ct.Register(() =>
                    {
                        // 拿 node.List 判断"还在排队"还是"已经被放行"：
                        //   还在排队 → 摘掉即可；
                        //   已被放行 → 票已经算在我头上了，必须还回去，否则这张票就丢了。
                        bool giveBack = false;
                        lock (_lock)
                        {
                            if (node.List != null) _waiters.Remove(node);
                            else giveBack = true;
                        }
                        tcs.TrySetCanceled(ct);
                        if (giveBack) Release();
                    });
                }
            }

            try
            {
                await tcs.Task.ConfigureAwait(false);
            }
            finally
            {
                // 必须释放注册：cancelToken 是**任务级**的长生命周期令牌，
                // 每等一次都留一个注册的话，长下载会累积成千上万个回调，
                // 既占内存又让 Cancel 变慢。
                reg.Dispose();
            }
        }

        /// <summary>归还一张通行证，并唤醒下一个等待者（若有空位）。</summary>
        public void Release()
        {
            TaskCompletionSource<bool> wake = null;
            lock (_lock)
            {
                if (_inFlight > 0) _inFlight--;
                if (_waiters.Count > 0 && _inFlight < _limit)
                {
                    _inFlight++;
                    wake = _waiters.First.Value;
                    _waiters.RemoveFirst();
                }
            }
            if (wake != null)
                wake.TrySetResult(true);
        }
    }
}
