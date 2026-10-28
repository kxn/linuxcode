using System;
using System.Diagnostics.Tracing;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;

// Public managed APIs only. This does not load Unity business assemblies.
// Each invocation runs one phase; no trust override or certificate bypass.
public static class ManagedHttpCancellationSmoke
{
    static int checks;

    // No event payloads: names locate a stalled public networking phase
    // without logging URLs, addresses, credentials or certificate data.
    sealed class NetworkEvents : EventListener
    {
        protected override void OnEventSourceCreated(EventSource source)
        {
            if (source.Name == "System.Net.NameResolution" || source.Name == "System.Net.Sockets" ||
                source.Name == "System.Net.Security" || source.Name == "System.Net.Http")
                EnableEvents(source, EventLevel.Verbose, (EventKeywords)(-1L));
        }

        protected override void OnEventWritten(EventWrittenEventArgs item)
        {
            Console.WriteLine("MANAGED_HTTP_EVENT " + item.EventSource.Name + " " +
                (item.EventName ?? ("Event" + item.EventId)));
        }
    }

    static void Check(bool condition, string name)
    {
        if (!condition) throw new Exception("check failed: " + name);
        checks++;
        Console.WriteLine("MANAGED_HTTP_CHECK " + name);
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static void ThrowForStack()
    {
        throw new ApplicationException("own-stack-fixture");
    }

    static async Task Tasks()
    {
        int answer = await Task.Run(() => 21 * 2);
        Check(answer == 42, "threadpool-task");
        using (var completed = new ManualResetEventSlim(false))
        {
            ThreadPool.QueueUserWorkItem(state => completed.Set());
            Check(completed.Wait(2000), "threadpool-event");
        }
        try
        {
            await Task.Run((Action)ThrowForStack);
            throw new Exception("expected deliberate exception");
        }
        catch (ApplicationException error)
        {
            Check(error.Message == "own-stack-fixture", "exception-type-message");
            Check(error.StackTrace != null && error.StackTrace.Contains("ThrowForStack"), "exception-stack");
        }
        using (var cancellation = new CancellationTokenSource())
        {
            cancellation.CancelAfter(20);
            try
            {
                await Task.Delay(5000, cancellation.Token);
                throw new Exception("expected delay cancellation");
            }
            catch (OperationCanceledException error)
            {
                Check(cancellation.IsCancellationRequested, "delay-cancel-requested");
                Check(error.CancellationToken == cancellation.Token, "delay-cancel-token");
                Check(!String.IsNullOrEmpty(error.StackTrace), "delay-cancel-stack");
            }
        }
    }

    static async Task Request(string phase, string address)
    {
        Uri target = new Uri(address);
        bool isHttps = phase == "https";
        Check(target.Scheme == (isHttps ? "https" : "http"), "request-scheme");
        if (!isHttps) Check(target.IsLoopback, "http-loopback-only");
        using (var handler = new HttpClientHandler())
        {
            handler.UseProxy = false;
            using (var client = new HttpClient(handler))
            using (var cancellation = new CancellationTokenSource())
            {
                client.Timeout = TimeSpan.FromSeconds(8);
                if (phase == "cancel") cancellation.CancelAfter(100);
                try
                {
                    using (HttpResponseMessage response = await client.GetAsync(target, HttpCompletionOption.ResponseHeadersRead, cancellation.Token))
                    {
                        if (phase == "cancel") throw new Exception("expected cancellation before response headers");
                        Check(response.StatusCode == HttpStatusCode.OK, "http-status-200");
                        if (!isHttps)
                        {
                            string body = await response.Content.ReadAsStringAsync();
                            Check(body == "LINUXCODE_HTTP_FIXTURE_OK\n", "http-loopback-body");
                        }
                    }
                }
                catch (OperationCanceledException error)
                {
                    if (phase != "cancel") throw;
                    Check(cancellation.IsCancellationRequested, "http-cancel-requested");
                    Check(!String.IsNullOrEmpty(error.StackTrace), "http-cancel-stack");
                }
            }
        }
    }

    public static int Main()
    {
        EventListener listener = Environment.GetEnvironmentVariable("LINUXCODE_MANAGED_HTTP_TRACE") == "1" ? new NetworkEvents() : null;
        string phase = Environment.GetEnvironmentVariable("LINUXCODE_MANAGED_HTTP_PHASE") ?? "tasks";
        Console.WriteLine("MANAGED_HTTP_BEGIN " + phase);
        try
        {
            if (phase == "tasks") Tasks().GetAwaiter().GetResult();
            else if (phase == "http" || phase == "cancel" || phase == "https")
            {
                string address = Environment.GetEnvironmentVariable("LINUXCODE_MANAGED_HTTP_URL");
                if (String.IsNullOrEmpty(address)) throw new Exception("LINUXCODE_MANAGED_HTTP_URL required");
                Request(phase, address).GetAwaiter().GetResult();
            }
            else throw new Exception("unknown phase");
            Console.WriteLine("MANAGED_HTTP_COMPLETE " + phase + " CHECKS " + checks);
            return 0;
        }
        catch (Exception error)
        {
            for (Exception item = error; item != null; item = item.InnerException)
            {
                Console.WriteLine("MANAGED_HTTP_EXCEPTION type=" + item.GetType().FullName + " hresult=" + item.HResult);
                SocketException socketError = item as SocketException;
                if (socketError != null)
                    Console.WriteLine("MANAGED_HTTP_SOCKET_ERROR error_code=" + socketError.ErrorCode +
                        " socket_error_code=" + (int)socketError.SocketErrorCode);
                Console.WriteLine(item.StackTrace);
            }
            Console.WriteLine("MANAGED_HTTP_FAILED " + phase + " CHECKS " + checks);
            return 1;
        }
        finally
        {
            if (listener != null) listener.Dispose();
        }
    }
}
