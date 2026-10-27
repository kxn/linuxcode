using System.Runtime.InteropServices;
using UnityEngine;

public sealed class NativePodSmoke : MonoBehaviour
{
#if UNITY_IOS && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern int LinuxcodePodAnswer();
#endif
    private void Start()
    {
#if UNITY_IOS && !UNITY_EDITOR
        Debug.Log("Linuxcode CocoaPods answer: " + LinuxcodePodAnswer());
#else
        Debug.Log("Linuxcode Unity export smoke scene");
#endif
    }
}
