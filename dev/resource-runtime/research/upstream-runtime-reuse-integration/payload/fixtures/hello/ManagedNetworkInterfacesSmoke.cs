using System;
using System.Net.NetworkInformation;

// Exercise the public network API without collecting or printing host addresses.
public static class ManagedNetworkInterfacesSmoke
{
    public static int Main()
    {
        string phase = "enumerate";
        try
        {
            Console.WriteLine("NETWORK_BEGIN " + phase);
            NetworkInterface[] interfaces = NetworkInterface.GetAllNetworkInterfaces();
            Console.WriteLine("NETWORK_ENUMERATED " + interfaces.Length);
            foreach (NetworkInterface item in interfaces)
            {
                phase = "physical-address";
                int length = item.GetPhysicalAddress().GetAddressBytes().Length;
                phase = "interface-type";
                NetworkInterfaceType type = item.NetworkInterfaceType;
                phase = "ipv4-support";
                bool ipv4 = item.Supports(NetworkInterfaceComponent.IPv4);
                Console.WriteLine("NETWORK_INTERFACE type=" + type + " address_length=" + length + " ipv4=" + ipv4);
            }
            Console.WriteLine("NETWORK_COMPLETE");
            return 0;
        }
        catch (Exception exception)
        {
            Console.WriteLine("NETWORK_FAILED phase=" + phase + " type=" + exception.GetType().FullName + " hresult=" + exception.HResult);
            NetworkInformationException network = exception as NetworkInformationException;
            if (network != null)
                Console.WriteLine("NETWORK_NATIVE_ERROR " + network.ErrorCode);
            Console.WriteLine(exception.StackTrace);
            return 1;
        }
    }
}
